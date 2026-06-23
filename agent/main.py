import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
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
    
    # Load conversation history from Redis
    history_key = f"conversation:{conversation_id}:messages"
    history_raw = engine.redis.get(history_key)
    
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
    global graph
    if not graph:
        # Fallback if startup lifespan didn't run or completed with empty graph
        tools = await get_mcp_tools()
        graph = build_graph(tools)
        
    result = await graph.ainvoke({
        "messages": messages_list,
        "tokens_used": 0,
        "blocked": False,
        "block_reason": ""
    })
    
    # The final message content
    final_message = result["messages"][-1]
    response_text = final_message.content
    is_blocked = result.get("blocked", False)
    
    # Save the updated history to Redis
    updated_messages = result["messages"]
    serialized_history = [message_to_dict(msg) for msg in updated_messages]
    engine.redis.set(history_key, json.dumps(serialized_history))
    
    # Log to policy:logs for the dashboard UI
    log_entry = {
        "conversation_id": conversation_id,
        "user_message": req.message,
        "agent_response": response_text,
        "blocked": is_blocked
    }
    engine.redis.lpush("policy:logs", json.dumps(log_entry))
    engine.redis.ltrim("policy:logs", 0, 99)
    
    return {
        "response": response_text,
        "blocked": is_blocked,
        "conversation_id": conversation_id
    }

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
