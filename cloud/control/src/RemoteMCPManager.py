import asyncio
import httpx
import os
import threading
import traceback
from urllib.parse import urlsplit, urlunsplit

#from sympy import python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client

MCP_HTTP_CONNECT_TIMEOUT_SECONDS = float(os.getenv("MCP_HTTP_CONNECT_TIMEOUT_SECONDS", "10"))
MCP_HTTP_READ_TIMEOUT_SECONDS = float(os.getenv("MCP_HTTP_READ_TIMEOUT_SECONDS", "30"))
MCP_TOOL_CALL_TIMEOUT_SECONDS = float(os.getenv("MCP_TOOL_CALL_TIMEOUT_SECONDS", "60"))

class RemoteMCPManager:
    def __init__(self):
        self.session = None
        self.transport_ctx = None
        self.http_client = None
        self.read = None
        self.write = None
        self.loop = asyncio.new_event_loop()
        # Elindítjuk az eseményhurkot egy külön szálon
        self.thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self.thread.start()

    def _run_event_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def ssh_connect(self, user, host, python_path, script_path):
        """Szinkron csatlakozás: megvárja, amíg kiépül az SSH alagút."""
        args = ["-q",
                "-o", "BatchMode=yes",
                "-o", "StrictHostKeyChecking=accept-new",
                "-o", "ConnectTimeout=5",
                  f"{user}@{host}", f"{python_path}/python3", script_path]
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
        try:
            return future.result()
        except BaseException as e:
            excs = getattr(e, 'exceptions', None)
            if excs:
                print(f"SSE connect failed — {len(excs)} sub-exception(s):")
                for i, sub in enumerate(excs):
                    print(f"  [{i}] {type(sub).__name__}: {sub}")
                    traceback.print_exception(type(sub), sub, sub.__traceback__)
            raise

    def str_connect(self, url):
        """Blocking connect for streamable HTTP MCP transport."""
        print(f"Connecting to Streamable HTTP MCP server at {url}")
        future = asyncio.run_coroutine_threadsafe(self._str_establish(url), self.loop)
        try:
            return future.result()
        except BaseException as e:
            excs = getattr(e, 'exceptions', None)
            if excs:
                print(f"Streamable HTTP connect failed — {len(excs)} sub-exception(s):")
                for i, sub in enumerate(excs):
                    print(f"  [{i}] {type(sub).__name__}: {sub}")
                    traceback.print_exception(type(sub), sub, sub.__traceback__)
            raise

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

    def _prepare_url_and_headers(self, url):
        parsed = urlsplit(url)
        robot_ip = os.getenv("ROBOT_IP")
        if parsed.hostname == "robot_ip" and robot_ip:
            # Keep userinfo and port if present, only replace host.
            netloc = parsed.netloc
            if "@" in netloc:
                userinfo, hostport = netloc.rsplit("@", 1)
                _, _, port = hostport.partition(":")
                rebuilt_hostport = f"{robot_ip}:{port}" if port else robot_ip
                netloc = f"{userinfo}@{rebuilt_hostport}"
            else:
                _, _, port = netloc.partition(":")
                netloc = f"{robot_ip}:{port}" if port else robot_ip

            url = urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))

        headers = {}
        mcp_key = os.getenv("MCP_KEY")
        if mcp_key:
            headers["Authorization"] = f"Bearer {mcp_key}"

        return url, headers

    async def _sse_establish(self, url):
        url, headers = self._prepare_url_and_headers(url)

        print(f"SSE connection to {url}")
        self.transport_ctx = sse_client(url, headers=headers)
        self.read, self.write = await self.transport_ctx.__aenter__()
        self.session = ClientSession(self.read, self.write)
        await self.session.__aenter__()
        await self.session.initialize()
        return True

    async def _str_establish(self, url):
        url, headers = self._prepare_url_and_headers(url)

        print(
            f"Streamable HTTP connection to {url} "
            f"(bearer_auth={'enabled' if 'Authorization' in headers else 'disabled'})"
        )
        timeout = httpx.Timeout(
            connect=MCP_HTTP_CONNECT_TIMEOUT_SECONDS,
            read=MCP_HTTP_READ_TIMEOUT_SECONDS,
            write=MCP_HTTP_READ_TIMEOUT_SECONDS,
            pool=MCP_HTTP_CONNECT_TIMEOUT_SECONDS,
        )
        self.http_client = httpx.AsyncClient(headers=headers, timeout=timeout)
        self.transport_ctx = streamable_http_client(url, http_client=self.http_client)
        self.read, self.write, _ = await self.transport_ctx.__aenter__()
        self.session = ClientSession(self.read, self.write)
        await self.session.__aenter__()
        await self.session.initialize()
        return True

    async def _close_async(self):
        session = self.session
        transport_ctx = self.transport_ctx
        http_client = self.http_client

        self.session = None
        self.transport_ctx = None
        self.http_client = None
        self.read = None
        self.write = None

        if session is not None:
            await session.__aexit__(None, None, None)

        if transport_ctx is not None:
            await transport_ctx.__aexit__(None, None, None)

        if http_client is not None:
            await http_client.aclose()

    def close(self):
        """Close the MCP session and transport resources."""
        future = asyncio.run_coroutine_threadsafe(self._close_async(), self.loop)
        try:
            return future.result()
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(timeout=1)

    def get_tools_blocking(self):
        """Blocking call to list tools"""
        if not self.session:
            raise Exception("No connection!")
        
        future = asyncio.run_coroutine_threadsafe(self.session.list_tools(), self.loop)
        return future.result() # Itt vár (blokkol)

    async def call_tool_async(self, tool_name, args):
        """Async tool call"""
        return await self.session.call_tool(tool_name, arguments=args)

    def call_tool_blocking(self, tool_name, args, timeout_seconds: float | None = None):
        """Blocking tool call — for use outside async context."""
        future = asyncio.run_coroutine_threadsafe(
            self.call_tool_async(tool_name, args), self.loop
        )
        wait_timeout = MCP_TOOL_CALL_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
        return future.result(timeout=wait_timeout)