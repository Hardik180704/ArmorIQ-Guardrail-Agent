# ArmorIQ — Guarded AI Agent with MCP Support

A full-stack AI agent security system with real-time guardrails, 
MCP tool integration, and a live policy dashboard.

## Architecture
User → FastAPI → LangGraph Agent → Policy Engine → MCP Servers
                                      ↓
                                Redis (live rules)
                                      ↓
                                Next.js Dashboard

## Stack

- **Agent**: LangGraph + Claude (claude-sonnet-4-5)
- **MCP Servers**: FastMCP (custom SecureVault) + Exa (remote)
- **Policy Engine**: Pure Python + Redis
- **Backend**: FastAPI
- **Frontend**: Next.js + Tailwind + shadcn/ui
- **Observability**: LangSmith
- **Infrastructure**: Docker Compose

## MCP Servers

| Server | Type | Tools |
|--------|------|-------|
| SecureVault | Custom (FastMCP) | write_record, read_record, delete_record, list_records, get_audit_log |
| Exa | Remote | web_search_exa, web_fetch_exa |

## Policy Engine — Rule Types

| Type | Description |
|------|-------------|
| `block` | Permanently block a tool from executing |
| `require_approval` | Require human approval before execution |
| `input_validation` | Validate tool arguments against rules |
| `budget` | Block agent if token budget exceeded |

## Setup & Running

### With Docker (Recommended)

1. Clone the repo
2. Copy `.env.sample` to `.env` and fill in your API keys
3. Run:
```bash
docker compose up --build
```
4. Open `http://localhost:3000`

### Without Docker

**Backend:**
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn agent.main:app --reload --port 8000
```

**Dashboard:**
```bash
cd dashboard
npm install
npm run dev
```

**Redis:**
```bash
docker run -d -p 6379:6379 redis:alpine
```

## Edge Cases Handled

- **MCP server crash** → error caught, agent returns graceful error message
- **Prompt injection** → detected at API level before reaching LLM
- **Conflicting rules** → first matching rule wins (ordered evaluation)
- **Approver offline** → returns PENDING status, tool not executed
- **Token budget exceeded** → agent blocked mid-conversation

## Project Structure
armoriq-assignment/
├── agent/
│   ├── main.py          # FastAPI server
│   ├── graph.py         # LangGraph agent loop
│   └── mcp_client.py    # MCP server connections
├── policy/
│   └── engine.py        # Policy engine (self-contained)
├── mcp_server/
│   └── server.py        # Custom SecureVault MCP server
├── dashboard/           # Next.js frontend
├── docker-compose.yml
├── Dockerfile
└── .env.sample
