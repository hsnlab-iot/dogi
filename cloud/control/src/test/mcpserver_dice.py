import asyncio
import random

try:
    from mcp.server.models import InitializationOptions
    from mcp.server import NotificationOptions, Server
    from mcp.server.stdio import stdio_server
    import mcp.types as types
    MCP_AVAILABLE = True
except Exception:
    MCP_AVAILABLE = False


# Shared dice logic (can be used by MCP handler or fallback test)
def roll_dice(sides: int = 6) -> int:
    if sides < 1:
        raise ValueError("sides must be >= 1")
    return random.randint(1, sides)


if MCP_AVAILABLE:
    # 1. Initialize the Server
    server = Server("dice-server")

    # 2. Define the tool
    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="roll_dice",
                description="Rolls an N-sided dice and returns the result.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "sides": {"type": "integer", "minimum": 1}
                    },
                    "required": [],
                },
            )
        ]

    # 3. Define the tool logic
    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict | None) -> types.CallToolResult:
        if name == "roll_dice":
            try:
                sides = 6
                if arguments and isinstance(arguments, dict):
                    sides = int(arguments.get("sides", 6))

                result = roll_dice(sides)

                return types.CallToolResult(
                    content=[
                        types.TextContent(type="text", text=f"🎲 Rolled a {sides}-sided dice: {result}")
                    ],
                    isError=False,
                )

            except Exception as e:
                return types.CallToolResult(
                    content=[types.TextContent(type="text", text=f"Internal Error: {str(e)}")],
                    isError=True,
                )

        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"Tool not found: {name}")],
            isError=True,
        )


    async def main():
        # Run the server using standard I/O (compatible with MCP stdio transport)
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="dice-server",
                    server_version="0.1.0",
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )


    if __name__ == "__main__":
        asyncio.run(main())

else:
    # Fallback test: run roll_dice locally and print result
    if __name__ == "__main__":
        print("mcp package not available — running fallback local test")
        for sides in (6, 20):
            result = roll_dice(sides)
            print(f"Rolled a {sides}-sided dice: {result}")
