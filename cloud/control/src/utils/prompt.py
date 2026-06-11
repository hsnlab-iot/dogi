import os
import json
import base64
import mimetypes
import io
import time
import datetime
import re

import config


def _reasoning_to_text(reasoning_value):
    if not reasoning_value:
        return ""

    if isinstance(reasoning_value, str):
        return reasoning_value

    if isinstance(reasoning_value, list):
        parts = []
        for item in reasoning_value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
            else:
                text = getattr(item, "text", None) or getattr(item, "content", None)
                if isinstance(text, str):
                    parts.append(text)
        return ''.join(parts)

    if isinstance(reasoning_value, dict):
        text = reasoning_value.get("text") or reasoning_value.get("content")
        if isinstance(text, str):
            return text

    text = getattr(reasoning_value, "text", None) or getattr(reasoning_value, "content", None)
    if isinstance(text, str):
        return text

    return str(reasoning_value)


def remove_reasoning(text):
    if not isinstance(text, str):
        return text
    # Remove <think>...</think> blocks
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    # Remove everything before a lone </think> tag (some LLMs omit the opening tag)
    text = re.sub(r'^.*?</think>', '', text, flags=re.DOTALL)
    return text.lstrip('\n').strip()


def _is_probable_base64(value):
    if not isinstance(value, str):
        return False

    stripped = ''.join(value.strip().split())
    if not stripped or len(stripped) % 4 != 0:
        return False

    try:
        base64.b64decode(stripped, validate=True)
        return True
    except Exception:
        return False


def _append_image_content(content_items, image, binary):
    if isinstance(image, str):
        if image.startswith('data:'):
            content_items.append({
                "type": "image_url",
                "image_url": {"url": image}
            })
            return

        if os.path.isfile(image):
            try:
                with open(image, 'rb') as f:
                    image_bytes = f.read()
            except (FileNotFoundError, IOError) as e:
                print(f"Warning: Could not load image {image}: {e}")
                return

            mime_type, _ = mimetypes.guess_type(image)
            if mime_type is None:
                mime_type = 'image/jpeg'
            image_data = base64.standard_b64encode(image_bytes).decode('utf-8')
            content_items.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{image_data}"}
            })
            return

        if _is_probable_base64(image):
            content_items.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image}"}
            })
            return

        print(f"Warning: Unsupported image string format: {image[:80]}...")
        return

    image_bytes = None
    if isinstance(image, (bytes, bytearray, memoryview)):
        image_bytes = bytes(image)
    elif hasattr(image, 'read') and callable(image.read):
        try:
            current_pos = image.tell() if hasattr(image, 'tell') and callable(image.tell) else None
            image_bytes = image.read()
            if current_pos is not None and hasattr(image, 'seek') and callable(image.seek):
                image.seek(current_pos)
        except Exception as e:
            print(f"Warning: Could not read image bytes from stream-like object: {e}")
            return

    if image_bytes is None:
        print(f"Warning: Unsupported image type {type(image)}; expected string path/data URL/base64 or bytes")
        return

    if binary:
        content_items.append({
            "type": "input_image",
            "image": image_bytes,
        })
        return

    image_data = base64.standard_b64encode(image_bytes).decode('utf-8')
    content_items.append({
        "type": "image_url",
        "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}
    })


def _to_jsonable(value):
    try:
        return value.model_dump()
    except Exception:
        pass

    try:
        return value.to_dict()
    except Exception:
        pass

    try:
        return json.loads(value.model_dump_json())
    except Exception:
        pass

    return str(value)


def _estimate_bytes(value):
    if value is None:
        return 0
    if isinstance(value, bytes):
        return len(value)
    if isinstance(value, bytearray):
        return len(value)
    if isinstance(value, memoryview):
        return len(value.tobytes())
    if isinstance(value, str):
        return len(value.encode('utf-8'))
    if isinstance(value, bool):
        return 4 if value else 5
    if isinstance(value, (int, float)):
        return len(str(value).encode('utf-8'))
    if isinstance(value, dict):
        total = 2  # braces
        for k, v in value.items():
            total += _estimate_bytes(str(k)) + _estimate_bytes(v)
        return total
    if isinstance(value, (list, tuple, set)):
        total = 2  # brackets
        for item in value:
            total += _estimate_bytes(item)
        return total

    return _estimate_bytes(_to_jsonable(value))


def _usage_to_dict(usage_obj):
    if usage_obj is None:
        return None
    usage_data = _to_jsonable(usage_obj)
    if isinstance(usage_data, dict):
        return usage_data
    return {"raw": str(usage_data)}


def _debug_openai_request(tag, request_kwargs):
    try:
        serialized = json.dumps(request_kwargs, ensure_ascii=False, indent=2)
    except TypeError:
        serialized = str(request_kwargs)

    print(f"[DEBUG][OpenAI][{tag}] request args:\n{serialized}")


def _debug_openai_response(tag, response):
    payload = None

    try:
        payload = response.model_dump()
    except Exception:
        pass

    if payload is None:
        try:
            payload = response.to_dict()
        except Exception:
            pass

    if payload is None:
        try:
            payload = json.loads(response.model_dump_json())
        except Exception:
            payload = str(response)

    try:
        serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    except TypeError:
        serialized = str(payload)

    print(f"[DEBUG][OpenAI][{tag}] response:\n{serialized}")


def _sanitize_for_json(value):
    # Handle common binary types
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray, memoryview)):
        try:
            b = bytes(value)
            return {"__bytes_base64__": base64.b64encode(b).decode('ascii')}
        except Exception:
            return str(value)
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            try:
                key = str(k)
            except Exception:
                key = repr(k)
            out[key] = _sanitize_for_json(v)
        return out
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_for_json(v) for v in value]

    # Fallback to structured conversions
    try:
        j = _to_jsonable(value)
        # If _to_jsonable returned something complex, sanitize it too
        if isinstance(j, (dict, list, tuple, set)):
            return _sanitize_for_json(j)
        return j
    except Exception:
        pass

    try:
        return str(value)
    except Exception:
        return None


def _maybe_write_log(kind, payload):
    """Write payload to log directory if configured.

    kind: 'request' or 'response' (used in filename)
    payload: object to serialize
    """
    try:
        log_dir = config.get_log_dir()
    except Exception:
        log_dir = None

    if not log_dir:
        return

    # Build timestamp YYYYmmddHHMMSSmmm
    now = datetime.datetime.utcnow()
    ts = now.strftime('%Y%m%d%H%M%S') + f"{int(now.microsecond/1000):03d}"
    filename = os.path.join(log_dir, f"{ts}_{kind}.json")

    safe = _sanitize_for_json(payload)
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(safe, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Warning: failed to write OpenAI {kind} log to {filename}: {e}")


def response_filter(response):
    # Remove any leading/trailing whitespace and unwanted characters
    response = response.strip()

    # Remove bold text marked with **, and followed by a ":"
    response = re.sub(r'\*\*[^*]+:\*\*', '', response)  # Remove bold text followed by ":"

    # Remove list markers that are a star with 3 spaces
    response = re.sub(r'^\s*\*\s{3}', '', response, flags=re.MULTILINE)

    # Remove all ** around words
    response = re.sub(r'\*\*(.*?)\*\*', r'\1', response)

    return response


# Cretae content items for prompt based on input prompt
# and images, with option to use binary image content
# when possible
def _build_content(prompt_text, images, binary = False):
    content_items = [{"type": "text", "text": prompt_text}]
    if images:
        for image in images:
            _append_image_content(content_items, image, binary)
    return content_items


def _build_statistics(request_payload, usage_obj, elapsed_seconds, images, stream, model):
    usage_dict = _usage_to_dict(usage_obj)
    stats = {
        "prompt_size_bytes": _estimate_bytes(request_payload),
        "messages_size_bytes": _estimate_bytes(request_payload.get("messages", [])),
        "tools_size_bytes": _estimate_bytes(request_payload.get("tools", [])),
        "images_count": len(images) if images else 0,
        "stream": bool(stream),
        "model": model,
        "elapsed_seconds": elapsed_seconds,
        "token_usage": usage_dict,
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
    }
    if isinstance(usage_dict, dict):
        stats["prompt_tokens"] = usage_dict.get("prompt_tokens")
        stats["completion_tokens"] = usage_dict.get("completion_tokens")
        stats["total_tokens"] = usage_dict.get("total_tokens")
    return stats


def prompt_with_tools(prompt, message_history=None, tools=None, images=None):

    messages = message_history if message_history else []

    # In dict, there may be multiple language versions; select the one matching the prompt language if available
    if isinstance(prompt, dict):
        # Import here to avoid circular imports
        from . import select_text
        prompt = select_text(prompt, config.get_prompt_language())

    # Tools result is a full messages payload,
    # so if prompt is a list, assume it's already
    #  the full messages payload and use it directly
    if isinstance(prompt, list):
        messages.extend(prompt)

    # Otherwise, treat prompt as text and build content
    else:
        if not messages:
            messages.append({
                "role": "system",
                "content": config.get_soul_content()
                })
        messages.append({
            "role": "user",
            "content": _build_content(prompt, images, config.get_openai_binary_images())
            })
    
    # If enable_thinking is not sent disable thinking
    if not config.get_openai_enable_thinking():
        messages.append(
            {"role": "assistant", "content": "<think></think>"}
            )

    model = None
    if images:
        model = config.get_vision_model()
        print(f"Prompting with {len(images)} images, using {model}")
    else:
        model = config.get_general_model()
        print(f"Prompting with text only, using {model}")

    extra_body = config.get_openai_general_extra_body(
        num_predict=config.get_openai_max_output_tokens()
    )

    request_kwargs = {
        "model": model,
        "messages": messages,
        "temperature": config.get_openai_prompt_temperature(),
        "frequency_penalty": config.get_openai_prompt_frequency_penalty(),
        "max_tokens": config.get_openai_max_output_tokens(),
        "extra_body": extra_body,
    }

    if tools is not None:
        request_kwargs['tools'] = tools

    openai_client = config.get_openai_client()

    now = time.time()
    
    _debug_openai_request("prompt", request_kwargs)
    _maybe_write_log('request', request_kwargs)
    response = openai_client.chat.completions.create(**request_kwargs)
    usage = getattr(response, "usage", None)
    _debug_openai_response("prompt", response)
    _maybe_write_log('response', response)

    elapsed = time.time() - now
    
    statistics = _build_statistics(request_kwargs, usage, elapsed, images, False, model)
    return response, messages, statistics


def prompt(prompt_text, images=None, stream=False):

    # In dict, there may be multiple language versions;
    # select the one matching the prompt language
    # if available
    if isinstance(prompt_text, dict):
        # Import here to avoid circular imports
        from . import select_text
        prompt_text = select_text(prompt_text, config.get_prompt_language())

    soul_prompt = config.get_soul_content()

    model = None
    if images:
        model = config.get_vision_model()
        print(f"Prompting {model} with {prompt_text} and {len(images)}")
    else:
        model = config.get_general_model()
        print(f"Prompting {model} with {prompt_text}")

    openai_client = config.get_openai_client()
    now = time.time()
    content = _build_content(prompt_text, images, config.get_openai_binary_images())
    extra_body = config.get_openai_general_extra_body(
        num_predict=config.get_openai_max_output_tokens()
    )
    thinking_enabled = config.get_openai_enable_thinking()

    messages = [
        {"role": "system", "content": soul_prompt},
        {"role": "user", "content": content},
    ]
    if not thinking_enabled:
        # Prefill answer
        #messages.append({"role": "assistant", "content": "<think></think>"})
        messages.append({"role": "assistant", "content": "Here is the direct response: "})

    request_kwargs = {
        "model": model,
        "messages": messages,
        "temperature": config.get_openai_prompt_temperature(),
        "frequency_penalty": config.get_openai_prompt_frequency_penalty(),
        "max_tokens": config.get_openai_max_output_tokens(),
        "extra_body": extra_body,
    }

    if stream:
        request_kwargs["stream"] = True

    _debug_openai_request("prompt", request_kwargs)
    _maybe_write_log('request', request_kwargs)

    if stream:
        usage = None

        stream_response = openai_client.chat.completions.create(**request_kwargs)

        full_response_parts = []
        full_reasoning_parts = []
        finish_reason = None
        reasoning_header_printed = False

        print("Streamed response:", end=" ", flush=True)
        for chunk in stream_response:
            if getattr(chunk, "usage", None) is not None:
                usage = chunk.usage

            if not getattr(chunk, "choices", None):
                continue

            choice = chunk.choices[0]
            delta = getattr(choice, "delta", None)
            piece = getattr(delta, "content", None) if delta is not None else None
            reasoning_piece = getattr(delta, "reasoning_content", None) if delta is not None else None

            reasoning_text = _reasoning_to_text(reasoning_piece)
            if reasoning_text:
                if not reasoning_header_printed:
                    print("\nStreamed reasoning:", end=" ", flush=True)
                    reasoning_header_printed = True
                print(reasoning_text, end="", flush=True)
                full_reasoning_parts.append(reasoning_text)

            if piece:
                if reasoning_header_printed:
                    print("\nStreamed response:", end=" ", flush=True)
                    reasoning_header_printed = False
                print(piece, end="", flush=True)
                full_response_parts.append(piece)

            if getattr(choice, "finish_reason", None) is not None:
                finish_reason = choice.finish_reason

        print()

        if finish_reason is not None:
            print(f"Finish Reason: {finish_reason}")
        if usage is not None:
            print(f"Usage: {usage}")
        if full_reasoning_parts:
            print(f"Reasoning: {''.join(full_reasoning_parts)}")
        elapsed = time.time() - now
        print(f"OpenAI ({model}) prompt stream time: {elapsed}")
        filtered_response = response_filter(''.join(full_response_parts))
        # Write assembled streaming response to log if configured
        try:
            resp_payload = {
                'full_response': ''.join(full_response_parts),
                'reasoning': ''.join(full_reasoning_parts),
                'usage': _sanitize_for_json(usage),
            }
            _maybe_write_log('response', resp_payload)
        except Exception:
            pass
        statistics = _build_statistics(request_kwargs, usage, elapsed, images, stream, model)

    else:
        usage = None
        response = openai_client.chat.completions.create(**request_kwargs)
        _debug_openai_response("prompt", response)
        _maybe_write_log('response', response)
        usage = getattr(response, "usage", None)

        elapsed = time.time() - now
        statistics = _build_statistics(request_kwargs, usage, elapsed, images, stream, model)

        print(f"Finish Reason: {response.choices[0].finish_reason}")
        print(f"Usage: {response.usage}")
        reasoning_text = _reasoning_to_text(getattr(response.choices[0].message, "reasoning_content", None))
        if reasoning_text:
            print(f"Reasoning: {reasoning_text}")
        if response.choices and response.choices[0].message and not getattr(response.choices[0].message, "content", None):
            # content is "" or not present
            if response.choices and response.choices[0].message and getattr(response.choices[0].message, "reasoning", None):
                response.choices[0].message.content = getattr(response.choices[0].message, "reasoning")
        filtered_response = response_filter(response.choices[0].message.content)

    print(f"OpenAI ({model}) prompt time: {statistics['elapsed_seconds']}")
    return filtered_response, statistics
