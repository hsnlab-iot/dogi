import sys
import json
import asyncio
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Memory")

MEMORY_FILE = "dogi_memory.txt"

@mcp.tool()
def save_info(info: str):
    """Elment egy fontos információt a felhasználóról vagy a világról."""
    with open(MEMORY_FILE, "a", encoding="utf-8") as f:
        f.write(info + "\n")
    return f"Megjegyeztem: {info}"

@mcp.tool()
def list_memories():
    """Kilistázza az összes eddig elmentett emléket."""
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "Még nincsenek emlékeim."

if __name__ == "__main__":
    mcp.run()
