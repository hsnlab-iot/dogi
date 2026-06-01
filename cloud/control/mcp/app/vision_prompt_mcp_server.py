import base64
import json
import os
import time
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

import requests
import uvicorn
from fastmcp import FastMCP
from openai import OpenAI


HOST = os.getenv("MCP_HOST", "0.0.0.0")
PORT = int(os.getenv("MCP_PORT", 5000))
HTTP_TIMEOUT_SECONDS = float(os.getenv("HTTP_TIMEOUT_SECONDS", "15"))

EXPECTED_KEY = os.getenv("MCP_KEY")
if not EXPECTED_KEY:
    raise RuntimeError("MCP_KEY environment variable must be set")

SNAPSHOT_URL = os.getenv("SNAPSHOT_URL")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
OPENAI_MODEL = os.getenv("OPENAI_MODEL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "not-needed")
OPENAI_IMAGE_INPUT_MODE = os.getenv("OPENAI_IMAGE_INPUT_MODE", "url").strip().lower()
OPENAI_IMAGE_DETAIL = os.getenv("OPENAI_IMAGE_DETAIL", "auto")
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "1024"))
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.0"))
OPENAI_ENABLE_THINKING = os.getenv("OPENAI_ENABLE_THINKING", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

if not SNAPSHOT_URL:
    raise RuntimeError("SNAPSHOT_URL environment variable must be set")
if not OPENAI_BASE_URL:
    raise RuntimeError("OPENAI_BASE_URL environment variable must be set")
if not OPENAI_MODEL:
    raise RuntimeError("OPENAI_MODEL environment variable must be set")
if OPENAI_IMAGE_INPUT_MODE not in {"url", "base64"}:
    raise RuntimeError("OPENAI_IMAGE_INPUT_MODE must be 'url' or 'base64'")

openai_client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url=OPENAI_BASE_URL,
    timeout=HTTP_TIMEOUT_SECONDS,
)

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
                print("Authentication failed!")
                return

        await self.inner_app(scope, receive, send)


def _to_data_url(image_bytes: bytes, mime_type: str) -> str:
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{image_b64}"


def _cache_busted_url(url: str) -> str:
    parts = urlsplit(url)
    query_items = parse_qsl(parts.query, keep_blank_values=True)
    query_items.append(("_ts", str(int(time.time() * 1000))))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query_items), parts.fragment))


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


def _call_openai_chat_completions(content_parts: list[dict]) -> str:
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

    request_payload = {
        "model": OPENAI_MODEL,
        "messages": messages,
        "max_tokens": OPENAI_MAX_TOKENS,
        "temperature": OPENAI_TEMPERATURE,
    }

    if not OPENAI_ENABLE_THINKING:
        request_payload["extra_body"] = {
            "enable_thinking": False,
            "think": False,
            "options": {
                "think": False,
            },
        }

    print("[vision_prompt][debug] OpenAI raw request:")
    print(json.dumps(request_payload, indent=2, ensure_ascii=False))

    completion = openai_client.chat.completions.create(**request_payload)

    print("[vision_prompt][debug] OpenAI raw response:")
    print(completion.model_dump_json(indent=2))

    if not completion.choices:
        raise RuntimeError("openai response does not contain choices")

    message = completion.choices[0].message
    content = getattr(message, "content", None)

    text = _extract_content_text(content)
    if text:
        return text

    # Fallback to raw model dump; some backends serialize content differently.
    message_dump = message.model_dump() if hasattr(message, "model_dump") else {}
    text = _extract_content_text(message_dump.get("content"))
    if text:
        return text

    dump_content = completion.model_dump() if hasattr(completion, "model_dump") else {}
    choices = dump_content.get("choices", []) if isinstance(dump_content, dict) else []
    if choices and isinstance(choices[0], dict):
        text = _extract_content_text(choices[0].get("message", {}).get("content"))
        if text:
            return text

    raise RuntimeError("openai response returned empty content")


mcp = FastMCP("vision-prompt")


@mcp.tool()
def vision_prompt(prompt: str) -> str:
    """Capture a snapshot through the camera and run a prompt on it."""
    if not prompt or not prompt.strip():
        raise ValueError("prompt must not be empty")

    snapshot_url = SNAPSHOT_URL
    prompt_text = prompt.strip()

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
        content_parts.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": _to_data_url(image_bytes, mime_type),
                    "detail": OPENAI_IMAGE_DETAIL,
                },
            }
        )

    text = _call_openai_chat_completions(content_parts)
    if not text:
        raise RuntimeError("prompt returned empty text")

    return text


mcp_app = mcp.http_app(transport="streamable-http")
app = APIKeyProtectedApp(mcp_app)


if __name__ == "__main__":
    print(f"Vision MCP Server starting on http://{HOST}:{PORT}/mcp (streamable-http)")
    print(f"Using snapshot URL: {SNAPSHOT_URL}")
    print(f"Using OpenAI base URL: {OPENAI_BASE_URL}")
    print(f"Using model: {OPENAI_MODEL}")
    print(f"Using image input mode: {OPENAI_IMAGE_INPUT_MODE}")
    print(f"Using thinking mode: {OPENAI_ENABLE_THINKING}")
    uvicorn.run(app, host=HOST, port=PORT)
