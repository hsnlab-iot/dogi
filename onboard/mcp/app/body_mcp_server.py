import os
import sys

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from mcp.server.fastmcp import FastMCP

sys.path.append("/app")
from dog_action import register_tools


HOST = os.getenv("MCP_HOST", "0.0.0.0")
PORT = int(os.getenv("MCP_PORT", 5000))
MCP_PATH = "/mcp"


def _extract_api_key(request: Request) -> str | None:
    api_key = request.headers.get("x-api-key")
    if api_key:
        return api_key

    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()

    return None


EXPECTED_KEY = os.getenv("MCP_KEY")
if not EXPECTED_KEY:
    raise RuntimeError("MCP_KEY environment variable must be set")


mcp = FastMCP("dogzilla")
register_tools(mcp)

app = FastAPI()
app.mount(MCP_PATH, mcp.http_app(transport="streamable-http"))


@app.middleware("http")
async def enforce_api_key(request: Request, call_next):
    if request.url.path.startswith(MCP_PATH):
        provided_key = _extract_api_key(request)
        if provided_key != EXPECTED_KEY:
            raise HTTPException(status_code=401, detail="Invalid API key")

    return await call_next(request)


if __name__ == "__main__":
    print(f"MCP Server starting on http://{HOST}:{PORT}{MCP_PATH} (streamable-http)")
    uvicorn.run(app, host=HOST, port=PORT)