import asyncio
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
import mcp.types as types

# 1. Initialize the Server
server = Server("test-server")

# 2. Define the tool
@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_high_five",
            description="Returns a virtual high five.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"}
                },
                "required": ["name"],
            },
        )
    ]

# 3. Define the tool logic
@server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> types.CallToolResult:
    if name == "get_high_five":
        try:
            user_name = arguments.get("name")

            # Application-level failure example
            if not user_name:
                return types.CallToolResult(
                    content=[types.TextContent(type="text", text="Error: Name is missing.")],
                    isError=True
                )

            # Success
            return types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text=f"✋ High five, {user_name}! The MCP connection is working!"
                    )
                ],
                isError=False # Default is False, but good for clarity
            )

        except Exception as e:
            # Catch unexpected logic errors
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=f"Internal Error: {str(e)}")],
                isError=True
            )

    # If the LLM tries to call a tool that doesn't exist
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=f"Tool not found: {name}")],
        isError=True
    )

async def main():
    # Run the server using standard I/O
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="test-server",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())