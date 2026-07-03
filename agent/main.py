import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    message_to_dict,
    messages_from_dict,
)

from agent.mcp_client import get_mcp_tools
from agent.graph import build_graph
from policy.engine import PolicyEngine

# Global variables for compiled graph and tools
graph = None
tools = None

async def ensure_tools_loaded():
    global tools, graph
    if tools is None:
        tools = await get_mcp_tools()
    if graph is None:
        graph = build_graph(tools)
    return tools

def log_policy_event(engine: PolicyEngine, entry: dict):
    engine.redis.lpush("policy:logs", json.dumps(entry))
    engine.redis.ltrim("policy:logs", 0, 99)

def append_conversation_message(engine: PolicyEngine, conversation_id: str, message: AIMessage):
    history_key = f"conversation:{conversation_id}:messages"
    history_raw = engine.redis.get(history_key)
    messages_list = []
    if history_raw:
        try:
            messages_list = messages_from_dict(json.loads(history_raw))
        except Exception as e:
            print(f"Error parsing history: {e}")
    messages_list.append(message)
    serialized_history = [message_to_dict(msg) for msg in messages_list]
    engine.redis.set(history_key, json.dumps(serialized_history))

@asynccontextmanager
async def lifespan(app: FastAPI):
    global graph, tools
    print("🚀 Initializing MCP client and compiling LangGraph agent...")
    tools = await get_mcp_tools()
    graph = build_graph(tools)
    print("✅ Initialization complete.")
    yield

app = FastAPI(lifespan=lifespan)

# Allow CORS for the dashboard frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str
    conversation_id: str = None

@app.post("/chat")
async def chat(req: ChatRequest):
    conversation_id = req.conversation_id or str(uuid.uuid4())
    
    engine = PolicyEngine()
    injection = engine._check_prompt_injection({"message": req.message})
    if injection:
        log_entry = {
            "conversation_id": conversation_id,
            "user_message": req.message,
            "agent_response": f"🚫 Prompt injection blocked: '{injection}'",
            "blocked": True
        }
        log_policy_event(engine, log_entry)
        return {
            "response": f"🚫 Prompt injection detected and blocked: '{injection}'",
            "blocked": True,
            "policy_status": "BLOCK",
            "conversation_id": conversation_id
        }
    
    # Load conversation history from Redis
    history_key = f"conversation:{conversation_id}:messages"
    tokens_key = f"conversation:{conversation_id}:tokens_used"
    history_raw = engine.redis.get(history_key)
    tokens_used = engine._coerce_int(engine.redis.get(tokens_key), default=0)
    
    if history_raw:
        try:
            serialized_messages = json.loads(history_raw)
            messages_list = messages_from_dict(serialized_messages)
        except Exception as e:
            print(f"Error parsing history: {e}")
            messages_list = []
    else:
        messages_list = []
        
    # Append the new user message
    messages_list.append(HumanMessage(content=req.message))
    
    # Run the graph
    await ensure_tools_loaded()
        
    result = await graph.ainvoke({
        "messages": messages_list,
        "tokens_used": tokens_used,
        "conversation_id": conversation_id,
        "policy_status": "ALLOW",
        "blocked": False,
        "block_reason": "",
        "pending_approvals": [],
        "pending_reason": "",
    })
    
    # The final message content
    final_message = result["messages"][-1]
    response_text = final_message.content
    is_blocked = result.get("blocked", False)
    policy_status = result.get("policy_status", "ALLOW")
    pending_approvals = result.get("pending_approvals", [])
    
    # Save the updated history to Redis
    updated_messages = result["messages"]
    serialized_history = [message_to_dict(msg) for msg in updated_messages]
    engine.redis.set(history_key, json.dumps(serialized_history))
    engine.redis.set(tokens_key, int(result.get("tokens_used", tokens_used)))
    
    # Log to policy:logs for the dashboard UI
    log_entry = {
        "conversation_id": conversation_id,
        "user_message": req.message,
        "agent_response": response_text,
        "blocked": is_blocked,
        "policy_status": policy_status,
        "pending_approvals": pending_approvals,
    }
    log_policy_event(engine, log_entry)
    
    return {
        "response": response_text,
        "blocked": is_blocked,
        "policy_status": policy_status,
        "pending_approvals": pending_approvals,
        "conversation_id": conversation_id
    }

class ApprovalResolution(BaseModel):
    reason: str = None

@app.get("/approvals")
def list_approvals(status: str = Query(default=None)):
    engine = PolicyEngine()
    return {"approvals": engine.list_approvals(status=status)}

@app.get("/approvals/{approval_id}")
def get_approval(approval_id: str):
    engine = PolicyEngine()
    approval = engine.get_approval(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    return {"approval": approval}

@app.post("/approvals/{approval_id}/approve")
async def approve_approval(approval_id: str, req: ApprovalResolution = None):
    engine = PolicyEngine()
    approval = engine.get_approval(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    if approval.get("status") != "pending":
        raise HTTPException(status_code=409, detail=f"Approval is already {approval.get('status')}")

    loaded_tools = await ensure_tools_loaded()
    tool_call = approval.get("tool_call") or {}
    tool_name = tool_call.get("name")
    selected_tool = next((tool for tool in loaded_tools if tool.name == tool_name), None)
    if not selected_tool:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

    try:
        tool_result = await selected_tool.ainvoke(tool_call.get("args") or {})
    except Exception as exc:
        updated = engine.update_approval(approval_id, {
            "status": "failed",
            "approved_reason": req.reason if req else None,
            "error": str(exc),
        })
        raise HTTPException(status_code=500, detail=f"Approved tool execution failed: {exc}")

    updated = engine.update_approval(approval_id, {
        "status": "approved",
        "approved_reason": req.reason if req else None,
        "result": str(tool_result),
    })
    response_text = f"✅ Approved tool '{tool_name}' executed.\n\n{tool_result}"
    append_conversation_message(
        engine,
        approval["conversation_id"],
        AIMessage(content=response_text),
    )
    log_policy_event(engine, {
        "conversation_id": approval["conversation_id"],
        "user_message": approval.get("user_message", ""),
        "agent_response": response_text,
        "blocked": False,
        "policy_status": "APPROVED",
        "approval_id": approval_id,
    })
    return {"status": "approved", "approval": updated, "result": str(tool_result)}

@app.post("/approvals/{approval_id}/reject")
def reject_approval(approval_id: str, req: ApprovalResolution = None):
    engine = PolicyEngine()
    approval = engine.get_approval(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    if approval.get("status") != "pending":
        raise HTTPException(status_code=409, detail=f"Approval is already {approval.get('status')}")

    updated = engine.update_approval(approval_id, {
        "status": "rejected",
        "rejection_reason": req.reason if req else None,
    })
    tool_name = (approval.get("tool_call") or {}).get("name", "tool")
    response_text = f"🚫 Approval rejected for tool '{tool_name}'."
    append_conversation_message(
        engine,
        approval["conversation_id"],
        AIMessage(content=response_text),
    )
    log_policy_event(engine, {
        "conversation_id": approval["conversation_id"],
        "user_message": approval.get("user_message", ""),
        "agent_response": response_text,
        "blocked": True,
        "policy_status": "REJECTED",
        "approval_id": approval_id,
    })
    return {"status": "rejected", "approval": updated}

class RuleModel(BaseModel):
    id: str = None
    type: str
    tool: str
    enabled: bool = True
    reason: str = None
    max_tokens: int = None
    field: str = None
    pattern: str = None
    max_length: int = None
    blocked_keywords: list[str] = None

@app.get("/rules")
def get_rules():
    engine = PolicyEngine()
    return {"rules": engine.get_rules()}

@app.post("/rules")
def add_rule(rule: RuleModel):
    engine = PolicyEngine()
    rule_dict = {k: v for k, v in rule.model_dump().items() if v is not None}
    if not rule_dict.get("id"):
        rule_dict["id"] = str(uuid.uuid4())
    engine.add_rule(rule_dict)
    return {"status": "success", "rule": rule_dict}

@app.delete("/rules/{rule_id}")
def delete_rule(rule_id: str):
    engine = PolicyEngine()
    engine.delete_rule(rule_id)
    return {"status": "success"}

@app.patch("/rules/{rule_id}/toggle")
def toggle_rule(rule_id: str, enabled: bool):
    engine = PolicyEngine()
    engine.toggle_rule(rule_id, enabled)
    return {"status": "success"}

@app.get("/logs")
def get_logs():
    engine = PolicyEngine()
    raw_logs = engine.redis.lrange("policy:logs", 0, -1)
    logs = []
    for item in raw_logs:
        try:
            logs.append(json.loads(item))
        except Exception:
            pass
    return {"logs": logs}
