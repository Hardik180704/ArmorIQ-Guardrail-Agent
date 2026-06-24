from fastmcp import FastMCP
from datetime import datetime
import os
import json
import redis

mcp = FastMCP("SecureVault")

redis_client = redis.Redis.from_url(
    os.getenv("REDIS_URL", "redis://localhost:6379"),
    decode_responses=True
)

def log_operation(operation: str, key: str, value: str = None):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "operation": operation,
        "key": key,
        "value": value
    }
    redis_client.rpush("vault:audit_log", json.dumps(entry))

@mcp.tool()
def write_record(key: str, value: str)->str:
    redis_client.hset("vault:records", key, value)
    log_operation("WRITE", key, value)
    return f"✅ Record '{key}' written successfully."

@mcp.tool()
def read_record(key: str)->str:
    val = redis_client.hget("vault:records", key)
    if val is None:
        return f"Record '{key}' not found."
    log_operation("READ", key)
    return f"📖 Record '{key}': {val}"

@mcp.tool()
def delete_record(key: str)->str:
    deleted_count = redis_client.hdel("vault:records", key)
    if deleted_count == 0:
        return f"Record '{key}' not found."
    log_operation("DELETE", key)
    return f"🗑️ Record '{key}' deleted successfully."

@mcp.tool()
def list_records()->str:
    keys = redis_client.hkeys("vault:records")
    if not keys:
        return "📭 Vault is empty"
    log_operation("LIST", "all")
    keys_str = "\n".join(f"  • {k}" for k in keys)
    return f"📋 Stored records:\n{keys_str}"

@mcp.tool()
def get_audit_log() -> str:
    raw_log = redis_client.lrange("vault:audit_log", 0, -1)
    if not raw_log:
        return "📭 No operations logged yet"

    log_lines = []
    for entry_str in raw_log:
        try:
            entry = json.loads(entry_str)
            line = f"[{entry['timestamp']}] {entry['operation']} → key='{entry['key']}'"
            if entry.get('value'):
                line += f", value='{entry['value']}'"
            log_lines.append(line)
        except Exception:
            pass
    
    return "📜 Audit Log:\n" + "\n".join(log_lines)

# -- RUN --
if __name__ == "__main__":
    mcp.run(transport="stdio")