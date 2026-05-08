import base64
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, ImageContent, TextContent

mcp = FastMCP("RobotVision")

@mcp.tool()
async def capture_view() -> CallToolResult:
    """Captures a real-time image from the robot's primary camera."""

    # 1. Load image data from file located next to this script
    view_path = Path(__file__).resolve().parent / "view.jpg"
    with view_path.open("rb") as f:
        image_data = f.read()
    
    # 2. Base64 encode the binary data
    base64_image = base64.b64encode(image_data).decode("utf-8")
    
    # 3. Return a CallToolResult with both text and image content
    return CallToolResult(
        content=[
            TextContent(
                type="text", 
                text=f"[Image captured from robot dog perspective]"
            ),
            ImageContent(
                type="image",
                data=base64_image,
                mimeType="image/jpeg"
            )
        ]
    )

if __name__ == "__main__":
    mcp.run()