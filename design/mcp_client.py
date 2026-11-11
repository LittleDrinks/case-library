import json
import sys
import urllib.request


class McpClient:
    def __init__(self, url="http://localhost:4401/mcp"):
        self.url = url
        self.session_id = None
        self.next_id = 0
        result = self.request("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "case-library-design", "version": "1.0"},
        })
        self.protocol = result["protocolVersion"]
        self.notify("notifications/initialized")

    def request(self, method, params):
        self.next_id += 1
        request_id = self.next_id
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        response = self.send(payload)
        if "error" in response:
            raise RuntimeError(response["error"])
        return response["result"]

    def notify(self, method):
        self.send({"jsonrpc": "2.0", "method": method})

    def send(self, payload):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        request = urllib.request.Request(
            self.url, data=json.dumps(payload).encode(), headers=headers, method="POST",
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            self.session_id = response.headers.get("mcp-session-id", self.session_id)
            body = response.read().decode()
        if not body:
            return {}
        for line in body.splitlines():
            if line.startswith("data:"):
                return json.loads(line.removeprefix("data:").strip())
        return json.loads(body)

    def call_tool(self, name, arguments=None):
        return self.request("tools/call", {"name": name, "arguments": arguments or {}})


def main():
    client = McpClient()
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        result = client.request("tools/list", {})
    elif len(sys.argv) > 1:
        arguments = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
        result = client.call_tool(sys.argv[1], arguments)
    else:
        raise SystemExit("用法：mcp_client.py list 或 mcp_client.py <tool> '<arguments>'")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
