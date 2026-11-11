import json
import os
import subprocess
import sys
from pathlib import Path


class McpClient:
    def __init__(self):
        self.script = Path(__file__).resolve().parents[1] / "tools/penpot/mcp.cjs"

    def invoke(self, *arguments):
        result = subprocess.run(
            ["node", str(self.script), *arguments],
            env={**os.environ, "PENPOT_JSON_RESPONSE": "1"},
            capture_output=True, text=True, timeout=240, check=False,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        return json.loads(result.stdout)

    def call_tool(self, name, arguments=None):
        return self.invoke("tool", name, json.dumps(arguments or {}, ensure_ascii=False))


def main():
    client = McpClient()
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        result = client.invoke("list")
    elif len(sys.argv) > 1:
        arguments = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
        result = client.call_tool(sys.argv[1], arguments)
    else:
        raise SystemExit("用法：mcp_client.py list 或 mcp_client.py <tool> '<JSON参数>'")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
