from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages
import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    tokens_used: int
    blocked: bool
    block_reason: str

model = ChatAnthropic(
    model="claude-sonnet-4-5",
    api_key=os.getenv("ANTHROPIC_API_KEY")
)

def agent_node(state: AgentState):
    print("Agent is thinking...")
    messages = state["messages"]

    response = model_with_tools.invoke(messages)

    print(f"Agent response: {response.content[:100] if response.content else 'Tool call requested'}")

    return {
        "messages": [response],
        "tokens_used": state.get("tokens_used", 0) + response.usage_metadata.get("output_tokens", 0) if hasattr(response, 'usage_metadata') and response.usage_metadata else state.get("tokens_used", 0)
    }

def guardrail_node(state: AgentState):
    print("Guardrail is checking...")
    messages = state["messages"]
    last_message = messages[-1]

    if not hasattr(last_message, 'tool_calls') or not last_message.tool_calls:
        return state

    from policy.engine import PolicyEngine
    engine = PolicyEngine()

    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]

        decision = engine.evaluate(
            tool_name = tool_name,
            tool_args = tool_args,
            context = {"tokens_used": state.get("tokens_used",0)}
        )

        print(f"🛡️ Tool '{tool_name}' → {decision.status}")
        
        if decision.status == "BLOCK":
            return {
                "blocked": True,
                "block_reason": decision.reason,
                "messages": state["messages"]
            }
    
    return {"blocked": False, "messages": state["messages"]}

def blocked_node(state: AgentState):
    reason = state.get("block_reason", "Policy violation")
    print(f"🚫 Blocked: {reason}")
    return {
        "messages": [AIMessage(content=f"🚫 Action blocked by policy: {reason}")]
    }

def should_continue(state: AgentState):
    messages = state["messages"]
    last_message = messages[-1]

    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        return "policy"
    
    return END

def policy_decision(state: AgentState):
    if state.get("blocked"):
        return "blocked"
    return "tools"

def build_graph(tools: list):
    global model_with_tools
    model_with_tools = model.bind_tools(tools)

    graph = StateGraph(AgentState)

    graph.add_node("agent", agent_node)
    graph.add_node("policy", guardrail_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_node("blocked", blocked_node)

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
            "blocked": "blocked" 
        }
    )

    graph.add_edge("tools", "agent")

    graph.add_edge("blocked", END)

    return graph.compile()

async def run_agent(user_message: str):
    from agent.mcp_client import get_mcp_tools

    tools = await get_mcp_tools()
    print(f"✅ {len(tools)} tools loaded")

    graph = build_graph(tools)

    result = await graph.ainvoke({
        "messages": [HumanMessage(content=user_message)],
        "tokens_used": 0,
        "blocked": False,
        "block_reason": ""
    })

    final_message = result["messages"][-1]
    return final_message.content

if __name__ == "__main__":
    
    async def test():
        response = await run_agent("Delete the record with key test")
        print(f"\n✅ Final response: {response}")
    
    asyncio.run(test())



