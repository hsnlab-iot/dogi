import base64
import json
import os
import sys
import time
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl
from contextlib import contextmanager
from typing import Optional, Dict, Any
import socketio
import asyncio
import threading

import requests
import uvicorn
from fastmcp import FastMCP
from openai import OpenAI

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


# Configuration loading
config_path = os.getenv("VP_CONFIG")
EXPECTED_KEY = os.getenv("MCP_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_KEY", "not-needed")

if not config_path:
    raise RuntimeError("VP_CONFIG environment variable must be set")

if not os.path.exists(config_path):
    raise RuntimeError(f"Config file not found: {config_path}")

with open(config_path, "rb") as f:
    CONFIG = tomllib.load(f)

# Server configuration
SERVER_CONFIG = CONFIG.get("server", {})
HOST = SERVER_CONFIG.get("host", "0.0.0.0")
PORT = SERVER_CONFIG.get("port", 5000)
HTTP_TIMEOUT_SECONDS = float(SERVER_CONFIG.get("http_timeout_seconds", 15))
if not EXPECTED_KEY:
    raise RuntimeError("'server.api_key' must be set in config file")

# Logging configuration
LOG_LEVELS = {"ERROR": 0, "WARNING": 1, "INFO": 2, "DEBUG": 3}
LOG_CONFIG = CONFIG.get("logging", {})
DEBUG_LEVEL = LOG_LEVELS.get(LOG_CONFIG.get("level", "INFO").upper(), 2)

# Snapshot configuration
SNAPSHOT_CONFIG = CONFIG.get("snapshot", {})
SNAPSHOT_URL = SNAPSHOT_CONFIG.get("url")
if not SNAPSHOT_URL:
    raise RuntimeError("'snapshot.url' must be set in config file")

# SocketIO configuration (optional)
SOCKETIO_CONFIG = CONFIG.get("socketio", {})
SOCKETIO_URL = SOCKETIO_CONFIG.get("url")
SOCKETIO_EVENT = SOCKETIO_CONFIG.get("event", "snapshot")

# OpenAI configuration
OPENAI_CONFIG = CONFIG.get("openai", {})
OPENAI_BASE_URL = OPENAI_CONFIG.get("base_url")
OPENAI_MODEL = OPENAI_CONFIG.get("model")
OPENAI_TIMEOUT_SECONDS = float(OPENAI_CONFIG.get("timeout_seconds", 30))
OPENAI_IMAGE_INPUT_MODE = OPENAI_CONFIG.get("image_input_mode", "url").strip().lower()
OPENAI_IMAGE_DETAIL = OPENAI_CONFIG.get("image_detail", "auto")
OPENAI_MAX_TOKENS = int(OPENAI_CONFIG.get("max_tokens", 1024))
OPENAI_TEMPERATURE = float(OPENAI_CONFIG.get("temperature", 0.0))
OPENAI_ENABLE_THINKING = str(OPENAI_CONFIG.get("enable_thinking", False)).lower() in {
    "1", "true", "yes", "on"
}

if not OPENAI_BASE_URL:
    raise RuntimeError("'openai.base_url' must be set in config file")
if not OPENAI_MODEL:
    raise RuntimeError("'openai.model' must be set in config file")
if OPENAI_IMAGE_INPUT_MODE not in {"url", "base64"}:
    raise RuntimeError("'openai.image_input_mode' must be 'url' or 'base64'")

# Answer length configuration (maps to max tokens)
ANSWER_CONFIG = CONFIG.get("answer_lengths", {})
ANSWER_LENGTH_TOKENS = {
    "short": int(ANSWER_CONFIG.get("short", 256)),
    "medium": int(ANSWER_CONFIG.get("medium", 512)),
    "long": int(ANSWER_CONFIG.get("long", 2048)),
}

openai_client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url=OPENAI_BASE_URL,
    timeout=OPENAI_TIMEOUT_SECONDS,
)

def _log(level: str, msg: str):
    """Log message with level filtering based on DEBUG_LEVEL."""
    level_num = LOG_LEVELS.get(level.upper(), 2)
    if level_num <= DEBUG_LEVEL:
        print(f"[vision_prompt][{level.lower()}] {msg}", flush=True)
        sys.stdout.flush()


_socketio_lock = threading.Lock()


def _ensure_socketio_connected() -> bool:
    """Best-effort Socket.IO connection that never raises to callers."""
    global sio

    if not SOCKETIO_URL:
        return False

    with _socketio_lock:
        if sio is None:
            sio = socketio.Client()

        if sio.connected:
            return True

        try:
            sio.connect(SOCKETIO_URL)
            _log("DEBUG", f"SocketIO connected to {SOCKETIO_URL}")
            return True
        except Exception as e:
            _log("WARNING", f"SocketIO connection failed: {type(e).__name__}: {str(e)}")
            return False


def _send_snapshot_via_socketio(image: str):
    """Send snapshot to socketio server if configured."""
    if not _ensure_socketio_connected():
        return

    try:
        payload = {
            "data": image
        }
        sio.emit(SOCKETIO_EVENT, payload)
        _log("DEBUG", f"Snapshot sent to {SOCKETIO_URL} via event '{SOCKETIO_EVENT}'")
    except Exception as e:
        _log("WARNING", f"Failed to send snapshot via socketio: {type(e).__name__}: {str(e)}")

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
        request_path = scope.get("path", "")
        is_api = request_path.startswith(self.api_path)

        async def wrapped_receive():
            message = await receive()
            if is_api and message.get("type") == "http.disconnect":
                _log("DEBUG", f"ASGI receive: http.disconnect on {request_path}")
            return message

        async def wrapped_send(message):
            if is_api:
                msg_type = message.get("type", "")
                if msg_type == "http.response.start":
                    _log(
                        "DEBUG",
                        f"ASGI send: http.response.start status={message.get('status')} on {request_path}"
                    )
                elif msg_type == "http.response.body":
                    body = message.get("body") or b""
                    body_len = len(body)
                    _log(
                        "DEBUG",
                        f"ASGI send: http.response.body len={body_len} more_body={message.get('more_body', False)} on {request_path}"
                    )

            await send(message)
        
        if scope.get("type") == "http" and is_api:
            _log("DEBUG", f"Handling API request to {request_path}")
            provided_key = _extract_api_key(scope.get("headers", []))
            if provided_key != EXPECTED_KEY:
                _log("WARNING", f"Auth failed for {request_path}")
                await wrapped_send(
                    {
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [(b"content-type", b"application/json")],
                    }
                )
                await wrapped_send(
                    {
                        "type": "http.response.body",
                        "body": b'{"detail":"Invalid API key"}',
                        "more_body": False,
                    }
                )
                _log("WARNING", "Authentication failed!")
                return
            _log("DEBUG", f"Auth passed for {request_path}, forwarding to inner app")

        await self.inner_app(scope, wrapped_receive, wrapped_send)


def _to_data_url(image_bytes: bytes, mime_type: str) -> str:
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{image_b64}"


def _snapshot_binary(url: str) -> tuple[bytes, str]:
    session = requests.Session()
    response = session.get(url, timeout=HTTP_TIMEOUT_SECONDS)
    response.raise_for_status()
    mime_type = response.headers.get("Content-Type", "image/jpeg").split(";")[0].strip() or "image/jpeg"
    return response.content, mime_type


def _extract_content_text(content: object) -> str:
    if isinstance(content, str):
        text = content.strip()
        if text:
            return text

    if isinstance(content, dict):
        for key in ("content", "text", "output_text", "reasoning"):
            value = content.get(key)
            text = _extract_content_text(value)
            if text:
                return text

    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                item_type = str(item.get("type", "")).lower()
                if item_type in {"text", "output_text"}:
                    value = item.get("text", "")
                    if value:
                        text_parts.append(str(value))
                continue

            # Handle SDK objects like ChatCompletionMessageContentPartText.
            item_type = str(getattr(item, "type", "")).lower()
            if item_type in {"text", "output_text"}:
                value = getattr(item, "text", "")
                if value:
                    text_parts.append(str(value))
        text = "\n".join(part.strip() for part in text_parts if part and part.strip()).strip()
        if text:
            return text

    return ""


def _call_openai_chat_completions(content_parts: list[dict], max_tokens: int | None = None) -> str:
    messages: list[dict] = []
    if not OPENAI_ENABLE_THINKING:
        messages.append(
            {
                "role": "system",
                "content": "Keep reasoning internal and output only the final answer. /no_think",
            }
        )
        messages.append(
            {
                "role": "assistant",
                "content": "<think>\nThinking skipped.\n</think>\n",
            }
        )

    messages.append(
        {
            "role": "user",
            "content": content_parts,
        }
    )

    effective_max_tokens = max_tokens if max_tokens is not None else OPENAI_MAX_TOKENS
    request_payload = {
        "model": OPENAI_MODEL,
        "messages": messages,
        "max_tokens": effective_max_tokens,
        "temperature": OPENAI_TEMPERATURE,
    }

    if not OPENAI_ENABLE_THINKING:
        request_payload["extra_body"] = {
            "enable_thinking": False,
            "think": False,
            "options": {
                "think": False,
            },
            "chat_template_kwargs": {
                "enable_thinking": False
            },
        }

    _log("DEBUG", "OpenAI raw request:")
    _log("DEBUG", json.dumps(request_payload, indent=2, ensure_ascii=False))
    _log("DEBUG", f"Calling OpenAI chat.completions at {OPENAI_BASE_URL} with timeout {OPENAI_TIMEOUT_SECONDS}s")
    sys.stdout.flush()

    try:
        _log("DEBUG", "Starting OpenAI API call...")
        sys.stdout.flush()
        completion = openai_client.chat.completions.create(**request_payload)
        _log("DEBUG", "OpenAI API call completed successfully")
        sys.stdout.flush()
    except Exception as e:
        error_msg = f"OpenAI call failed with error: {type(e).__name__}: {str(e)}"
        _log("ERROR", error_msg)
        sys.stdout.flush()
        raise RuntimeError(error_msg) from e

    _log("DEBUG", "OpenAI raw response:")
    _log("DEBUG", completion.model_dump_json(indent=2))
    sys.stdout.flush()

    if not completion.choices:
        _log("ERROR", "OpenAI response has no choices")
        raise RuntimeError("openai response does not contain choices")

    message = completion.choices[0].message
    content = getattr(message, "content", None)
    _log("DEBUG", f"Extracted message content type: {type(content).__name__}")

    text = _extract_content_text(content)
    if text:
        _log("DEBUG", f"Successfully extracted text: {text[:100]}..." if len(text) > 100 else f"Successfully extracted text: {text}")
        return text

    # Fallback to raw model dump; some backends serialize content differently.
    _log("DEBUG", "Primary extraction failed, trying message.model_dump()")
    message_dump = message.model_dump() if hasattr(message, "model_dump") else {}
    text = _extract_content_text(message_dump.get("content"))
    if text:
        _log("DEBUG", f"Successfully extracted text from model_dump: {text[:100]}..." if len(text) > 100 else f"Successfully extracted text from model_dump: {text}")
        return text

    text = _extract_content_text(message_dump.get("reasoning"))
    if text:
        _log("DEBUG", f"Successfully extracted reasoning from model_dump: {text[:100]}..." if len(text) > 100 else f"Successfully extracted reasoning from model_dump: {text}")
        return text

    _log("DEBUG", "Second extraction failed, trying completion.model_dump()")
    dump_content = completion.model_dump() if hasattr(completion, "model_dump") else {}
    choices = dump_content.get("choices", []) if isinstance(dump_content, dict) else []
    if choices and isinstance(choices[0], dict):
        text = _extract_content_text(choices[0].get("message", {}).get("content"))
        if text:
            _log("DEBUG", f"Successfully extracted text from completion.model_dump: {text[:100]}..." if len(text) > 100 else f"Successfully extracted text from completion.model_dump: {text}")
            return text

        text = _extract_content_text(choices[0].get("message", {}).get("reasoning"))
        if text:
            _log("DEBUG", f"Successfully extracted reasoning from completion.model_dump: {text[:100]}..." if len(text) > 100 else f"Successfully extracted reasoning from completion.model_dump: {text}")
            return text

    _log("ERROR", f"All extraction methods failed. dump_content keys: {list(dump_content.keys()) if isinstance(dump_content, dict) else 'not a dict'}")
    _log("DEBUG", f"Full response dump: {json.dumps(dump_content, indent=2, ensure_ascii=False, default=str)}")
    raise RuntimeError("openai response returned empty content")


mcp = FastMCP("vision-prompt")


@mcp.tool()
def vision_prompt(prompt: str, answer_length: str = "short") -> str:
    """Capture a fresh snapshot through the camera and run a prompt on it.
    
    Args:
        prompt: The prompt to send to the vision model
        answer_length: Response length preference - 'short' (256 tokens), 'medium' (512 tokens), or 'long' (2048 tokens)
    """
    try:
        started_at = time.time()
        _log("DEBUG", f"vision_prompt called with prompt: {prompt[:100]}..." if len(prompt) > 100 else f"vision_prompt called with prompt: {prompt}")
        _log("DEBUG", f"answer_length: {answer_length}")
        if not prompt or not prompt.strip():
            raise ValueError("prompt must not be empty")

        # Validate and get max tokens for answer length
        if answer_length not in ANSWER_LENGTH_TOKENS:
            raise ValueError(f"answer_length must be one of {list(ANSWER_LENGTH_TOKENS.keys())}, got '{answer_length}'")
        max_tokens = ANSWER_LENGTH_TOKENS[answer_length]
        _log("DEBUG", f"Using max_tokens={max_tokens} for answer_length='{answer_length}'")

        snapshot_url = SNAPSHOT_URL
        prompt_text = prompt.strip()
        _log("DEBUG", f"Starting vision_prompt processing")

        content_parts: list[dict] = [
            {
                "type": "text",
                "text": prompt_text,
            }
        ]

        if OPENAI_IMAGE_INPUT_MODE == "url":
            content_parts.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": snapshot_url,
                        "detail": OPENAI_IMAGE_DETAIL,
                    },
                }
            )
        else:
            image_bytes, mime_type = _snapshot_binary(snapshot_url)
            image_url = _to_data_url(image_bytes, mime_type)

            if SOCKETIO_URL:
                _send_snapshot_via_socketio(image_url)

            content_parts.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image_url,
                        "detail": OPENAI_IMAGE_DETAIL,
                    },
                }
            )

        _log("DEBUG", f"Calling OpenAI with {len(content_parts)} content parts")
        text = _call_openai_chat_completions(content_parts, max_tokens=max_tokens)
        if not text:
            _log("ERROR", "OpenAI returned empty text")
            raise RuntimeError("prompt returned empty text")

        result_preview = text[:100] + "..." if len(text) > 100 else text
        _log("INFO", f"vision_prompt RETURNING RESULT: {result_preview}")
        _log("DEBUG", f"Return value type: {type(text).__name__}, length: {len(text)}")
        _log("DEBUG", f"vision_prompt elapsed: {time.time() - started_at:.3f}s")
        sys.stdout.flush()
        _log("DEBUG", "[PRE-RETURN] About to return from vision_prompt")
        sys.stdout.flush()
        return text
    except Exception as e:
        _log("ERROR", f"vision_prompt failed: {type(e).__name__}: {str(e)}")
        import traceback
        _log("DEBUG", f"[TRACEBACK] {traceback.format_exc()}")
        sys.stdout.flush()
        raise


mcp_app = mcp.http_app(transport="streamable-http")
app = APIKeyProtectedApp(mcp_app)
sio = None

if __name__ == "__main__":
    print(f"Vision MCP Server starting on http://{HOST}:{PORT}/mcp (streamable-http)", flush=True)
    print(f"Config file: {config_path}", flush=True)
    print(f"Using snapshot URL: {SNAPSHOT_URL}", flush=True)
    print(f"Using OpenAI base URL: {OPENAI_BASE_URL}", flush=True)
    print(f"Using model: {OPENAI_MODEL}", flush=True)
    print(f"Using image input mode: {OPENAI_IMAGE_INPUT_MODE}", flush=True)
    print(f"Using thinking mode: {OPENAI_ENABLE_THINKING}", flush=True)
    print(f"HTTP timeout: {HTTP_TIMEOUT_SECONDS}s", flush=True)
    print(f"Debug level: {list(LOG_LEVELS.keys())[DEBUG_LEVEL]}", flush=True)
    print(f"Available answer lengths: {list(ANSWER_LENGTH_TOKENS.keys())}", flush=True)
    if SOCKETIO_URL:
        print(f"SocketIO snapshot support enabled: {SOCKETIO_URL} (event: '{SOCKETIO_EVENT}')", flush=True)
    else:
        print("SocketIO snapshot support: disabled", flush=True)
    sys.stdout.flush()

    if SOCKETIO_URL:
        _ensure_socketio_connected()

    uvicorn.run(app, host=HOST, port=PORT)
