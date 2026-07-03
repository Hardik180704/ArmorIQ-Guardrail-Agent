from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages
import os
from dotenv import load_dotenv

load_dotenv()

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    tokens_used: int
    conversation_id: str
    policy_status: str
    blocked: bool
    block_reason: str
    pending_approvals: list
    pending_reason: str

model = ChatAnthropic(
    model="claude-sonnet-4-5",
    api_key=os.getenv("ANTHROPIC_API_KEY")
)

def agent_node(state: AgentState):
    print("Agent is thinking...")
    messages = state["messages"]

    response = model_with_tools.invoke(messages)

    print(f"Agent response: {response.content[:100] if response.content else 'Tool call requested'}")

    tokens_used = state.get("tokens_used", 0)
    if hasattr(response, 'usage_metadata') and response.usage_metadata:
        usage = response.usage_metadata
        tokens_used += usage.get("total_tokens") or usage.get("output_tokens", 0)

    return {
        "messages": [response],
        "tokens_used": tokens_used,
    }

def guardrail_node(state: AgentState):
    print("Guardrail is checking...")
    messages = state["messages"]
    last_message = messages[-1]

    if not hasattr(last_message, 'tool_calls') or not last_message.tool_calls:
        return state

    from policy.engine import PolicyEngine
    engine = PolicyEngine()

    blocked_tool_messages = []
    pending_tool_messages = []
    pending_approvals = []
    blocked_reason = ""
    pending_reason = ""
    is_blocked = False
    is_pending = False
    user_message = _latest_user_message(messages)
    decisions = []

    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        tool_id = tool_call.get("id")

        decision = engine.evaluate(
            tool_name = tool_name,
            tool_args = tool_args,
            context = {"tokens_used": state.get("tokens_used", 0)}
        )

        print(f"🛡️ Tool '{tool_name}' → {decision.status}")
        decisions.append((tool_call, decision))
        
        if decision.status == "BLOCK":
            is_blocked = True
            blocked_reason = decision.reason
            blocked_tool_messages.append(ToolMessage(
                content=f"Error: Action blocked by policy: {decision.reason}",
                tool_call_id=tool_id
            ))

    if is_blocked:
        # Provide block responses for all tool calls in the request to satisfy the API contract
        for tool_call in last_message.tool_calls:
            tool_id = tool_call.get("id")
            if not any(tm.tool_call_id == tool_id for tm in blocked_tool_messages):
                blocked_tool_messages.append(ToolMessage(
                    content="Error: Execution skipped because another tool in the request was blocked by policy.",
                    tool_call_id=tool_id
                ))
        return {
            "policy_status": "BLOCK",
            "blocked": True,
            "block_reason": blocked_reason,
            "messages": blocked_tool_messages
        }

    for tool_call, decision in decisions:
        if decision.status != "PENDING_APPROVAL":
            continue
        is_pending = True
        pending_reason = decision.reason
        tool_id = tool_call.get("id")
        approval = engine.create_pending_approval(
            conversation_id=state.get("conversation_id", ""),
            tool_call={
                "id": tool_id,
                "name": tool_call["name"],
                "args": tool_call["args"],
            },
            reason=decision.reason,
            user_message=user_message,
        )
        pending_approvals.append(approval)
        pending_tool_messages.append(ToolMessage(
            content=f"Pending approval: {decision.reason}. Approval id: {approval['id']}",
            tool_call_id=tool_id
        ))

    if is_pending:
        # Provide tool responses for all requested calls so the message history remains valid.
        for tool_call in last_message.tool_calls:
            tool_id = tool_call.get("id")
            if not any(tm.tool_call_id == tool_id for tm in pending_tool_messages):
                pending_tool_messages.append(ToolMessage(
                    content="Execution skipped because another tool in the request is pending approval.",
                    tool_call_id=tool_id
                ))
        return {
            "policy_status": "PENDING_APPROVAL",
            "blocked": False,
            "pending_reason": pending_reason,
            "pending_approvals": pending_approvals,
            "messages": pending_tool_messages
        }
    
    return {"policy_status": "ALLOW", "blocked": False, "messages": []}

def _latest_user_message(messages: list) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""

def blocked_node(state: AgentState):
    reason = state.get("block_reason", "Policy violation")
    print(f"🚫 Blocked: {reason}")
    return {
        "messages": [AIMessage(content=f"🚫 Action blocked by policy: {reason}")]
    }

def pending_approval_node(state: AgentState):
    approvals = state.get("pending_approvals", [])
    approval_ids = ", ".join(approval["id"] for approval in approvals)
    reason = state.get("pending_reason", "Tool execution requires approval")
    print(f"⏸️ Pending approval: {approval_ids}")
    return {
        "messages": [
            AIMessage(
                content=f"⏸️ Action pending approval: {reason}. Approval id(s): {approval_ids}"
            )
        ]
    }

def should_continue(state: AgentState):
    messages = state["messages"]
    last_message = messages[-1]

    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        return "policy"
    
    return END

def policy_decision(state: AgentState):
    policy_status = state.get("policy_status")
    if policy_status == "BLOCK" or state.get("blocked"):
        return "blocked"
    if policy_status == "PENDING_APPROVAL":
        return "pending_approval"
    return "tools"

def build_graph(tools: list):
    global model_with_tools
    model_with_tools = model.bind_tools(tools)

    graph = StateGraph(AgentState)

    graph.add_node("agent", agent_node)
    graph.add_node("policy", guardrail_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_node("blocked", blocked_node)
    graph.add_node("pending_approval", pending_approval_node)

    graph.set_entry_point("agent")

    graph.add_conditional_edges(
        "agent",
        should_continue,
        {
            "policy": "policy",
            END: END             
        }
    )

    graph.add_conditional_edges(
        "policy",
        policy_decision,
        {
            "tools": "tools",
            "blocked": "blocked",
            "pending_approval": "pending_approval",
        }
    )

    graph.add_edge("tools", "agent")

    graph.add_edge("blocked", END)
    graph.add_edge("pending_approval", END)

    return graph.compile()

async def run_agent(user_message: str):
    from agent.mcp_client import get_mcp_tools

    tools = await get_mcp_tools()
    print(f"✅ {len(tools)} tools loaded")

    graph = build_graph(tools)

    result = await graph.ainvoke({
        "messages": [HumanMessage(content=user_message)],
        "tokens_used": 0,
        "conversation_id": "",
        "policy_status": "ALLOW",
        "blocked": False,
        "block_reason": "",
        "pending_approvals": [],
        "pending_reason": "",
    })

    final_message = result["messages"][-1]
    return final_message.content
