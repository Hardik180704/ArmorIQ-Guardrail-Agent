from fastmcp import FastMCP
from datetime import datetime

mcp = FastMCP("SecureVault")

vault: dict[str, str] = {}
audit_log: list[dict] = []

def log_operation(operation: str, key: str, value: str = None):
    audit_log.append({
        "timestamp": datetime.now().isoformat(),
        "operation": operation,
        "key": key,
        "value": value
    })

@mcp.tool()
def write_record(key: str, value: str)->str:
    vault[key] = value
    log_operation("WRITE", key, value)
    return f"✅ Record '{key}' written successfully."

@mcp.tool()
def read_record(key: str)->str:
    if key not in vault:
        return f"Record '{key}' not found."
    log_operation("READ", key)
    return f"📖 Record '{key}': {vault[key]}"

@mcp.tool()
def delete_record(key: str)->str:
    if key not in vault:
        return f"Record '{key}' not found."
    del vault[key]
    log_operation("DELETE", key)
    return f"🗑️ Record '{key}' deleted successfully."

@mcp.tool()
def list_records()->str:
    if not vault:
        return "📭 Vault is empty"
    log_operation("LIST", "all")
    keys = "\n".join(f"  • {k}" for k in vault.keys())
    return f"📋 Stored records:\n{keys}"

@mcp.tool()
def get_audit_log() -> str:
    if not audit_log:
        return "📭 No operations logged yet"

    log_lines = []
    for entry in audit_log:
        line = f"[{entry['timestamp']}] {entry['operation']} → key='{entry['key']}'"
        if entry['value']:
            line += f", value='{entry['value']}'"
        log_lines.append(line)
    
    return "📜 Audit Log:\n" + "\n".join(log_lines)

# -- RUN --
if __name__ == "__main__":
    mcp.run(transport="stdio")