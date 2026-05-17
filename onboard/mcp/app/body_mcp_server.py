import os
import sys

import uvicorn
from fastmcp import FastMCP

sys.path.append("/app")
from dog_action import register_tools


HOST = os.getenv("MCP_HOST", "0.0.0.0")
PORT = int(os.getenv("MCP_PORT", 5000))

EXPECTED_KEY = os.getenv("MCP_KEY")
if not EXPECTED_KEY:
    raise RuntimeError("MCP_KEY environment variable must be set")


def _extract_api_key(headers: list[tuple[bytes, bytes]]) -> str | None:
    for key, value in headers:
        if key.lower() == b"x-api-key":
            return value.decode("utf-8")
        if key.lower() == b"authorization":
            auth = value.decode("utf-8")
            if auth.lower().startswith("bearer "):
                return auth[7:].strip()

    return None


class APIKeyProtectedApp:
    def __init__(self, inner_app, api_path: str = "/mcp"):
        self.inner_app = inner_app
        self.api_path = api_path

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("path", "").startswith(self.api_path):
            provided_key = _extract_api_key(scope.get("headers", []))
            if provided_key != EXPECTED_KEY:
                await send(
                    {
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [(b"content-type", b"application/json")],
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": b'{"detail":"Invalid API key"}',
                        "more_body": False,
                    }
                )
                return

        await self.inner_app(scope, receive, send)


mcp = FastMCP("dogzilla")
register_tools(mcp)

mcp_app = mcp.http_app(transport="streamable-http")
app = APIKeyProtectedApp(mcp_app)


if __name__ == "__main__":
    print(f"MCP Server starting on http://{HOST}:{PORT}/mcp (streamable-http)")
    uvicorn.run(app, host=HOST, port=PORT)