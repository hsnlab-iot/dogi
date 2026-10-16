import os
import time
import socket
import pickle
import threading
import json
import json as _json
import asyncio
import httpx
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError

from typing import List, Dict, Any
from mcp.types import CallToolResult, ImageContent, TextContent

from fastmcp.client import Client
from fastmcp.client.transports import SSETransport, StreamableHttpTransport

import utils
import config

import socketio

from loguru import logger

logger.remove()
logger.add(
    lambda msg: print(msg, end=""),           # keep console output identical shape
    level="DEBUG",
    format="<green>{time:HH:mm:ss}</green> <level>{message}</level>",
)
logger.add(f"{config.get_log_dir()}/agent_{{time:YYYY-MM-DD}}.log",  
           rotation="1 day", enqueue=True,
           format="{time:HH:mm:ss.SSS} | {level} | {message}")


from pydantic_ai import Agent, RunContext
from pydantic_ai.toolsets import AbstractToolset
from pydantic_ai.mcp import ToolsetTool, MCPToolset
from pydantic_ai.tools import ToolDefinition
from pydantic_core import SchemaValidator
from pydantic_ai.messages import FunctionToolCallEvent, FunctionToolResultEvent
from pydantic_ai._cancel import CancellationToken
from pydantic_ai.models import Model


PORT = 5058
sio = socketio.Client()

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

config.init()
toolscfg = config.get_tools()

MCP_HEADERS = {
    'X-API-Key': os.getenv('MCP_KEY', 'none'),
    'X-SocketIO-Url': 'http://dogi:5058',
}
if config.get_vision_model():
    MCP_HEADERS['X-Llm-Model'] = config.get_vision_model()

CALL_TIMEOUT = 120.0   # or whatever your slowest tool needs

# Worker control globals
worker_lock = threading.Lock()
worker_thread = None
worker_stop_event = None
active_cancel_token = None
speak_enabled = False

# History context
message_history = []
current_agent = None


async def log_request(request: httpx.Request):
    body = request.content.decode('utf-8', errors='replace')
    logger.info(f"=== HTTP REQUEST {request.method} {request.url} ===")
    try:
        parsed = json.loads(request.content)
        logger.info(json.dumps(parsed, indent=2, ensure_ascii=False))
    except Exception:
        logger.info(request.content.decode('utf-8', errors='replace')[:5000])

def _merge_sse_chunks(body: str):
    """Merge OpenAI-style SSE chunks into one pretty JSON dict."""
    final = {}
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith('data:'):
            continue
        payload = line[5:].strip()
        if payload == '[DONE]':
            continue
        try:
            chunk = _json.loads(payload)
        except Exception:
            continue
        for key, value in chunk.items():
            if key == 'choices':
                final.setdefault('choices', [])
                for c in value:
                    idx = c.get('index', 0)
                    while len(final['choices']) <= idx:
                        final['choices'].append({'index': idx, 'message': {}})
                    msg = final['choices'][idx].setdefault('message', {})
                    delta = c.get('delta', {})
                    for field in ('content', 'reasoning', 'role'):
                        if delta.get(field):
                            msg[field] = msg.get(field, '') + delta[field]
                    for tc in delta.get('tool_calls', []) or []:
                        tcs = msg.setdefault('tool_calls', [])
                        i = tc.get('index', 0)
                        while len(tcs) <= i:
                            tcs.append({'function': {'name': '', 'arguments': ''}})
                        if tc.get('id'):
                            tcs[i]['id'] = tc['id']
                        if tc.get('function', {}).get('name'):
                            tcs[i]['function']['name'] += tc['function']['name']
                        if tc.get('function', {}).get('arguments'):
                            tcs[i]['function']['arguments'] += tc['function']['arguments']
                    if c.get('finish_reason'):
                        final['choices'][idx]['finish_reason'] = c['finish_reason']
            elif key in ('id', 'object', 'created', 'model', 'usage', 'system_fingerprint'):
                if key == 'usage' and value:
                    final[key] = value
                elif key not in final:
                    final[key] = value
    return final

async def log_response(response: httpx.Response):
    logger.info(f"=== HTTP RESPONSE {response.status_code} ===")
    await response.aread()
    body = response.content.decode('utf-8', errors='replace')
    if body.lstrip().startswith('data:') or 'chat.completion.chunk' in body[:2000]:
        merged = _merge_sse_chunks(body)
        logger.info(json.dumps(merged, indent=2, ensure_ascii=False))
    else:
        try:
            logger.info(json.dumps(_json.loads(body), indent=2, ensure_ascii=False))
        except Exception:
            logger.info(body[:5000])



def create_http_client():
    return httpx.AsyncClient(
        event_hooks={'request': [log_request], 'response': [log_response]},
        timeout=300.0,
    )



def _log_tools(params):
    """Kivételmentes tool-lista logolás."""
    if params is None:
        return
    try:
        defs = getattr(params, 'tool_defs', None) or []
        names = []
        for d in defs:
            if isinstance(d, str):
                names.append(d)
            else:
                names.append(getattr(d, 'name', repr(d)))
        logger.info(f"tools={names}")
    except Exception as e:
        logger.debug(f"tool logging failed: {e}")


class LoggingModel(Model):
    """Wraps a pydantic-ai model, logging request and response payloads."""
    def __init__(self, real_model):
        self._real = real_model

    def __getattr__(self, name):
        return getattr(self._real, name)   # delegate everything else

    @property
    def model_name(self) -> str:
        return self._real.model_name

    @property
    def system(self) -> str:
        return self._real.system

    async def request(self, *args, **kwargs):
        messages = args[0] if args else kwargs.get('messages', [])
        params = args[2] if len(args) > 2 else kwargs.get('model_request_parameters')
        logger.info("=== LLM REQUEST ===")
        for m in messages:
            logger.info(f"[{m.kind}] {getattr(m, 'content', m)}")
        _log_tools(params)

        response = await self._real.request(*args, **kwargs)

        logger.info("=== LLM RESPONSE ===")
        for part in response.parts:
            if part.part_kind == 'tool-call':
                logger.info(f"TOOL-CALL {part.tool_name} args={part.args}")
            else:
                logger.info(f"{part.part_kind}: {part.content}")
        return response

    def request_stream(self, *args, **kwargs):
        messages = args[0] if args else kwargs.get('messages', [])
        params = args[2] if len(args) > 2 else kwargs.get('model_request_parameters')

        logger.info("=== LLM REQUEST (stream) ===")
        for m in messages:
            content = getattr(m, 'content', m)
            if not isinstance(content, str):
                content = repr(content)
            logger.info(f"[{getattr(m, 'kind', '?')}] {content[:500]}")
        _log_tools(params)

        real_cm = self._real.request_stream(*args, **kwargs)

        class _LoggingStreamCM:
            async def __aenter__(self):
                return await real_cm.__aenter__()

            async def __aexit__(self, *exc):
                result = await real_cm.__aexit__(*exc)
                logger.info("=== LLM STREAM END ===")
                return result

        return _LoggingStreamCM()

    def __repr__(self):
        return f"LoggingModel({self._real!r})"


def create_pydantic_model():
    """Constructs LLM model based on [llm].type in configuration."""
    llm_type = config.get_llm_type()
    url = config.get_llm_url()
    key = config.get_llm_key()
    model_name = config.get_llm_model()

    logger.info(f"Initializing model type='{llm_type}', model='{model_name}', url='{url}'")

    if llm_type == "ollama":
        logger.info(f"Building an ollama model: {url}, {model_name}")
        from pydantic_ai.providers.ollama import OllamaProvider
        from pydantic_ai.models.openai import OpenAIChatModel
        provider = OllamaProvider(base_url=url or None, api_key=key or None, http_client=create_http_client())
        return OpenAIChatModel(model_name, provider=provider)

    elif llm_type == "openai":
        logger.info(f"Building an openai model: {url}, {model_name}")
        from pydantic_ai.providers.openai import OpenAIProvider
        from pydantic_ai.models.openai import OpenAIChatModel
        provider = OpenAIProvider(base_url=url or None, api_key=key or None, http_client=create_http_client())
        return OpenAIChatModel(model_name, provider=provider)

    elif llm_type == "nim":
        logger.info(f"Building a nim model: {url}, {model_name}")
        from pydantic_ai.providers.openai import OpenAIProvider
        from pydantic_ai.models.openai import OpenAIChatModel
        provider = OpenAIProvider(base_url=url or None, api_key=key or None, http_client=create_http_client())
        return OpenAIChatModel(model_name, provider=provider)

    elif llm_type == "google":
        logger.info(f"Building a google model: {url}, {model_name}")
        from pydantic_ai.providers.google import GoogleProvider
        from pydantic_ai.models.google import GoogleModel
        provider = GoogleProvider(api_key=key, base_url=url or None, http_client=create_http_client())
        return GoogleModel(model_name, provider=provider)

    else:
        provider = None
        return None


async def probe_sse(url):
    async with Client(SSETransport(url, headers=MCP_HEADERS), timeout=5.0) as c:
        tools = await c.list_tools()
        return [t.name for t in tools]


async def probe_streamable(url):
    async with Client(StreamableHttpTransport(url, headers=MCP_HEADERS), timeout=5.0) as c:
        tools = await c.list_tools()
        return [t.name for t in tools]


async def build_toolsets():
    toolsets = []
    all_tools = []  # (server_url, [tool_names]) — None if down

    for entry in toolscfg:
        kind, url = entry.split('!', 1)

        try:
            if kind == 'sse':
                tools = await asyncio.wait_for(probe_sse(url), 5)
                toolsets.append(MCPToolset(Client(SSETransport(url, headers=MCP_HEADERS), timeout=CALL_TIMEOUT)))
            elif kind == 'str':
                tools = await asyncio.wait_for(probe_streamable(url), 5)
                toolsets.append(MCPToolset(Client(StreamableHttpTransport(url, headers=MCP_HEADERS), timeout=CALL_TIMEOUT)))
            else:
                logger.warning(f"Unknown toolset kind '{kind}' in entry '{entry}'")
                continue

            all_tools.extend(tools)
            logger.info(f"{url} OK: {tools}")
        except Exception as e:
            logger.info(f"{url} UNAVAILABLE: {type(e).__name__}: {e}")

    return toolsets, all_tools

async def build_agent():
    """Builds and configures the Pydantic AI agent."""
    model = LoggingModel(create_pydantic_model())
    toolsets, tools = await build_toolsets()

    logger.debug(tools)
    sio.emit('ui_update', {'type': 'tools', 'data': tools})

    agent = Agent(model, toolsets = toolsets)

    @agent.system_prompt
    def dynamic_system_prompt(ctx: RunContext) -> str:
        return config.get_system_prompt()

    # Tool call event callbacks provided by Pydantic AI
    @agent.on_event(FunctionToolCallEvent)
    def on_tool_call(ctx: RunContext, event: FunctionToolCallEvent):
        part = event.part
        args = getattr(part, 'args', None)
        if isinstance(args, dict):
            args_dict = args
        elif isinstance(args, str):
            try:
                args_dict = json.loads(args)
            except Exception:
                args_dict = {'raw': args}
        elif hasattr(part, 'args_as_dict'):
            args_dict = part.args_as_dict()
        else:
            args_dict = None
        logger.info(f"TOOL CALL {part.tool_name} args={json.dumps(args_dict, ensure_ascii=False, default=str)}")
        sio.emit('ui_update', {'type': 'response', 'data': f'Tool call {part.tool_name} args={json.dumps(args_dict, ensure_ascii=False, default=str)}'})

    @agent.on_event(FunctionToolResultEvent)
    def on_tool_result(ctx: RunContext, event: FunctionToolResultEvent):
        part = event.part
        content = str(part.content)
        logger.info(f"TOOL RESULT {part.tool_name} [{part.tool_call_id}] -> {content}")
        logger.info(f"result meta: is_error={getattr(part, 'has_error', None)}")  # attribute name varies
        sio.emit('ui_update', {'type': 'tools_response', 'data': content[:500]})
        sio.emit('ui_update', {'type': 'response', 'data': 'Tools finished.'})


    return agent


@sio.event
def connect():
    logger.info("Agent connected to Flask server!")


@sio.on('client_new')
def handle_new():
    global message_history
    message_history = []
    logger.info("Conversation history cleared.")


@sio.on('client_speak')
def handle_speak(data):
    global speak_enabled
    if isinstance(data, dict):
        speak_enabled = bool(data.get('enabled', False))
    else:
        speak_enabled = bool(data)


@sio.on('client_abort')
def handle_abort(data=None):
    global worker_stop_event, active_cancel_token
    logger.info("Abort received.")
    if active_cancel_token:
        active_cancel_token.cancel()
    if worker_stop_event:
        worker_stop_event.set()


@sio.on('client_prompt')
def handle_prompt(data):
    global worker_thread, worker_stop_event, active_cancel_token, speak_enabled

    try:
        prompt_text = data.get('prompt', '') if isinstance(data, dict) else str(data)
    except Exception:
        prompt_text = str(data)

    if isinstance(data, dict) and 'speak' in data:
        speak_enabled = bool(data.get('speak'))

    sio.emit("ui_update", {"type": "prompt", "data": "abort"})

    with worker_lock:
        if worker_thread and worker_thread.is_alive():
            return

        worker_stop_event = threading.Event()
        active_cancel_token = CancellationToken()

        def worker(prompt_text, stop_event, cancel_token, should_speak):
            global message_history, current_agent
            started_time = time.time()
            try:
                sio.emit('ui_update', {"type": "response", "data": "Waiting for my brain..."})

                result = loop.run_until_complete(
                    current_agent.run(
                        prompt_text,
                        message_history=message_history or None,
                        cancellation_token=cancel_token
                    )
                )

                if hasattr(result, 'all_messages'):
                    message_history = list(result.all_messages())
                    last = message_history[-1]
                    content = getattr(last, 'content', last)
                    logger.info(f"=== LLM RESPONSE === {str(content)[:1000]}")

                elapsed = time.time() - started_time

                if stop_event.is_set() or cancel_token.cancelled:
                    sio.emit("ui_update", {"type": "prompt", "data": "prompt"})
                    return

                # Record message history
                if hasattr(result, 'all_messages'):
                    message_history = list(result.all_messages())

                # Collect usage stats
                logger.debug(result.usage)
                prompt_tokens = getattr(result.usage, 'input_tokens', 0) if hasattr(result, 'usage') else 0
                completion_tokens = getattr(result.usage, 'output_tokens', 0) if hasattr(result, 'usage') else 0
                total_tokens = getattr(result.usage, 'total_tokens', 0) if hasattr(result, 'usage') else 0

                stats = {
                    'prompt_tokens': prompt_tokens,
                    'completion_tokens': completion_tokens,
                    'total_tokens': total_tokens,
                    'elapsed_seconds': elapsed,
                    'prompt_size_bytes': len(prompt_text.encode('utf-8'))
                }
                logger.info(f"Statistics: {json.dumps(stats, ensure_ascii=False)}")
                sio.emit('ui_update', {"type": "stats", "data": stats})

                response_content = result.output
                logger.info(f"Output: {response_content}")
                if response_content:
                    sio.emit('ui_update', {"type": "response", "data": str(response_content)})
                    sio.emit('ui_update', {"type": "response", "data": f'[{round(elapsed, 1)}s]'})

                    if should_speak and not stop_event.is_set():
                        wav, duration = utils.tts_wav(str(response_content).strip())
                        utils.play_wav(wav)
                        time.sleep(duration)

            except Exception as e:
                err_msg = f"Error: {e}"
                logger.error(f"Error during agent execution: {e}")
                sio.emit('ui_update', {"type": "response", "data": err_msg, "error": True})
                import traceback
                traceback.print_exc()
            finally:
                with worker_lock:
                    globals()['worker_thread'] = None
                    globals()['worker_stop_event'] = None
                    globals()['active_cancel_token'] = None
                sio.emit("ui_update", {"type": "prompt", "data": "prompt"})

        worker_thread = sio.start_background_task(
            worker, prompt_text, worker_stop_event, active_cancel_token, speak_enabled
        )


def introduction():
    text = {
        'en': "I am ready with Pydantic AI agent. Give me a task!",
        'hu': "Készen állok a Pydantic AI ágenssel. Adj egy feladatot!"
    }
    xtext = utils.select_text(text, config.get_ui_language(), True)
    logger.info(xtext)
    wav, d = utils.tts_wav(xtext, config.get_ui_language() + "_intro_agent")
    utils.play_wav(wav)
    time.sleep(d)


if __name__ == '__main__':
    sio.connect(f'http://localhost:{PORT}', socketio_path='/socket.io/')

    current_agent = loop.run_until_complete(build_agent())

    sio.emit('ui_update', {'type': 'prompt', 'data': 'prompt'})

    utils.dogy_reset()
    introduction()

    sio.wait()
