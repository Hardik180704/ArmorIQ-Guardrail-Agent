import sys
from langchain_mcp_adapters.client import MultiServerMCPClient
import os
from dotenv import load_dotenv

load_dotenv()

MCP_SERVERS = {
    "securevault": {
        "command": sys.executable,
        "args": ["mcp_server/server.py"],
        "transport": "stdio",
        "env": os.environ.copy(),
    },
    "exa": {
        "url": f"https://mcp.exa.ai/mcp?exaApiKey={os.getenv('EXA_API_KEY')}",
        "transport": "streamable_http",
    }
}

async def get_mcp_tools():
    client = MultiServerMCPClient(MCP_SERVERS)
    tools = await client.get_tools()

    print(f"\n🔌 Connected to {len(MCP_SERVERS)} MCP servers")
    print(f"🛠️  Discovered {len(tools)} tools:\n")
    for tool in tools:
        print(f"  • {tool.name}: {tool.description[:60]}")

    return tools