import asyncio
import threading

#from sympy import python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client


class RemoteMCPManager:
    def __init__(self):
        self.session = None
        self.loop = asyncio.new_event_loop()
        # Elindítjuk az eseményhurkot egy külön szálon
        self.thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self.thread.start()

    def _run_event_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def ssh_connect(self, user, host, python_path, script_path):
        """Szinkron csatlakozás: megvárja, amíg kiépül az SSH alagút."""
        args = ["-q", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", f"{user}@{host}", f"{python_path}/python3", script_path]
        params = StdioServerParameters(
            command="ssh",
            args=args
        )
        
        # Future-t használunk, hogy megvárjuk az async inicializálást
        print(f"Connecting to remote MCP server {args}")
        future = asyncio.run_coroutine_threadsafe(self._ssh_establish(params), self.loop)
        return future.result() # Ez blokkol, amíg nem sikerül a connect

    def sse_connect(self, url):
        """Blocking connect — waits until SSE connection is established."""
        print(f"Connecting to SSE MCP server at {url}")
        future = asyncio.run_coroutine_threadsafe(self._sse_establish(url), self.loop)
        return future.result()

    async def _ssh_establish(self, params):
        # Megjegyzés: A kontextus kezelőket (ctx managers) itt óvatosan kell használni, 
        # mert ha kilépünk a függvényből, lezárják a streamet.
        # Ezért itt direkt módban indítjuk:
        self.transport_ctx = stdio_client(params)
        self.read, self.write = await self.transport_ctx.__aenter__()
        self.session = ClientSession(self.read, self.write)
        await self.session.__aenter__()
        await self.session.initialize()
        return True

    async def _sse_establish(self, url):
        self.transport_ctx = sse_client(url)
        self.read, self.write = await self.transport_ctx.__aenter__()
        self.session = ClientSession(self.read, self.write)
        await self.session.__aenter__()
        await self.session.initialize()
        return True

    def get_tools_blocking(self):
        """Ez a metódus szinkronban blokkol, amíg megjön a lista."""
        if not self.session:
            raise Exception("Nincs kapcsolat!")
        
        future = asyncio.run_coroutine_threadsafe(self.session.list_tools(), self.loop)
        return future.result() # Itt vár (blokkol)

    async def call_tool_async(self, tool_name, args):
        """Ez pedig már marad async, ha így kényelmesebb."""
        return await self.session.call_tool(tool_name, arguments=args)

    def call_tool_blocking(self, tool_name, args):
        """Blocking tool call — for use outside async context."""
        future = asyncio.run_coroutine_threadsafe(
            self.call_tool_async(tool_name, args), self.loop
        )
        return future.result()