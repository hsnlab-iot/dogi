import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
import threading

import uvicorn
from fastmcp import FastMCP

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


config_path = os.getenv("TODOS_CONFIG")
EXPECTED_KEY = os.getenv("MCP_KEY")

if not config_path:
    raise RuntimeError("TODOS_CONFIG environment variable must be set")

if not os.path.exists(config_path):
    raise RuntimeError(f"Config file not found: {config_path}")

with open(config_path, "rb") as f:
    CONFIG = tomllib.load(f)

SERVER_CONFIG = CONFIG.get("server", {})
HOST = SERVER_CONFIG.get("host", "0.0.0.0")
PORT = int(SERVER_CONFIG.get("port", 5001))

if not EXPECTED_KEY:
    raise RuntimeError("MCP_KEY environment variable must be set")

LOG_LEVELS = {"ERROR": 0, "WARNING": 1, "INFO": 2, "DEBUG": 3}
LOG_CONFIG = CONFIG.get("logging", {})
DEBUG_LEVEL = LOG_LEVELS.get(LOG_CONFIG.get("level", "INFO").upper(), 2)

TODOS_CONFIG = CONFIG.get("todos", {})
_storage_raw = TODOS_CONFIG.get("storage_dir", "./todos_data")
if os.path.isabs(str(_storage_raw)):
    TODOS_STORAGE_DIR = str(_storage_raw)
else:
    TODOS_STORAGE_DIR = os.path.abspath(
        os.path.join(os.path.dirname(config_path), str(_storage_raw))
    )

TODOS_MAX_ITEMS_PER_SPACE = int(TODOS_CONFIG.get("max_items_per_space", 1000))
VALID_TODO_PRIORITIES = {"low", "medium", "high"}
VALID_TODO_STATUSES = {"open", "done"}


def _log(level: str, msg: str):
    level_num = LOG_LEVELS.get(level.upper(), 2)
    if level_num <= DEBUG_LEVEL:
        print(f"[todos_mcp][{level.lower()}] {msg}", flush=True)
        sys.stdout.flush()


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

        async def wrapped_send(message):
            if is_api and message.get("type") == "http.response.start":
                _log(
                    "DEBUG",
                    f"Response status={message.get('status')} path={request_path}",
                )
            await send(message)

        if scope.get("type") == "http" and is_api:
            provided_key = _extract_api_key(scope.get("headers", []))
            if provided_key != EXPECTED_KEY:
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
                _log("WARNING", f"Authentication failed for path {request_path}")
                return

        await self.inner_app(scope, receive, wrapped_send)


_todos_lock = threading.Lock()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize_space(space: str) -> str:
    candidate = (space or "").strip()
    if not candidate:
        return datetime.now(timezone.utc).date().isoformat()

    try:
        return datetime.strptime(candidate, "%Y-%m-%d").date().isoformat()
    except ValueError as e:
        raise ValueError("space must be a date in YYYY-MM-DD format") from e


def _ensure_storage_dir() -> None:
    os.makedirs(TODOS_STORAGE_DIR, exist_ok=True)


def _space_file_path(space: str) -> str:
    return os.path.join(TODOS_STORAGE_DIR, f"{space}.json")


def _new_space_document(space: str) -> dict:
    now = _utc_now_iso()
    return {
        "schema_version": 1,
        "space": space,
        "created_at": now,
        "updated_at": now,
        "items": [],
    }


def _load_space_document(space: str) -> dict:
    _ensure_storage_dir()
    path = _space_file_path(space)
    if not os.path.exists(path):
        return _new_space_document(space)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        return _new_space_document(space)

    data.setdefault("schema_version", 1)
    data.setdefault("space", space)
    data.setdefault("created_at", _utc_now_iso())
    data.setdefault("updated_at", _utc_now_iso())
    if not isinstance(data.get("items"), list):
        data["items"] = []
    return data


def _save_space_document(space: str, doc: dict) -> None:
    _ensure_storage_dir()
    doc["space"] = space
    doc["updated_at"] = _utc_now_iso()

    path = _space_file_path(space)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def _list_spaces() -> list[str]:
    _ensure_storage_dir()
    spaces: list[str] = []
    for entry in os.listdir(TODOS_STORAGE_DIR):
        if not entry.endswith(".json"):
            continue
        candidate = entry[:-5]
        try:
            spaces.append(_normalize_space(candidate))
        except ValueError:
            continue
    return sorted(set(spaces))


def _parse_tags(tags: str) -> list[str]:
    if not tags.strip():
        return []
    values = [tag.strip() for tag in tags.split(",") if tag.strip()]
    return list(dict.fromkeys(values))


def _find_todo(todo_id: str, space: str | None = None) -> tuple[str, dict, int]:
    search_spaces = [space] if space else _list_spaces()
    for sp in search_spaces:
        doc = _load_space_document(sp)
        for idx, item in enumerate(doc.get("items", [])):
            if item.get("id") == todo_id:
                return sp, doc, idx
    raise ValueError(f"todo not found: {todo_id}")


mcp = FastMCP("todos")


@mcp.tool()
def todos(
    action: str,
    title: str = "",
    todo_id: str = "",
    space: str = "",
    details: str = "",
    priority: str = "medium",
    tags: str = "",
    include_done: bool = True,
    limit: int = 50,
) -> str:
    """Date-scoped todo manager.

    Actions:
    - add: create a todo in a date space (YYYY-MM-DD, default=today)
    - list: list todos in one space
    - check: get one todo and completion state
    - complete: mark todo done
    - reopen: mark todo open
    - update: update title/details/priority/tags
    - delete: remove todo
    - summary: count open/done todos in one or all spaces
    - spaces: list all available date spaces
    """
    started_at = time.time()
    action_clean = (action or "").strip().lower()
    priority_clean = (priority or "").strip().lower()

    valid_actions = {
        "add",
        "list",
        "check",
        "complete",
        "reopen",
        "update",
        "delete",
        "summary",
        "spaces",
    }
    if action_clean not in valid_actions:
        raise ValueError(
            "action must be one of: add, list, check, complete, reopen, update, delete, summary, spaces"
        )

    if priority_clean and priority_clean not in VALID_TODO_PRIORITIES:
        raise ValueError("priority must be one of: low, medium, high")

    limit = max(1, min(int(limit), 500))

    with _todos_lock:
        if action_clean == "spaces":
            return json.dumps(
                {
                    "ok": True,
                    "action": "spaces",
                    "spaces": _list_spaces(),
                    "storage_dir": TODOS_STORAGE_DIR,
                },
                ensure_ascii=False,
                indent=2,
            )

        target_space = _normalize_space(space)

        if action_clean == "add":
            title_clean = title.strip()
            if not title_clean:
                raise ValueError("title is required for add")

            doc = _load_space_document(target_space)
            items = doc.get("items", [])
            if len(items) >= TODOS_MAX_ITEMS_PER_SPACE:
                raise RuntimeError(
                    f"space {target_space} reached max capacity ({TODOS_MAX_ITEMS_PER_SPACE})"
                )

            now = _utc_now_iso()
            item = {
                "id": uuid.uuid4().hex[:12],
                "title": title_clean,
                "details": details.strip(),
                "priority": priority_clean or "medium",
                "status": "open",
                "created_at": now,
                "updated_at": now,
                "completed_at": None,
                "tags": _parse_tags(tags),
            }
            items.append(item)
            doc["items"] = items
            _save_space_document(target_space, doc)
            return json.dumps(
                {
                    "ok": True,
                    "action": "add",
                    "space": target_space,
                    "item": item,
                    "elapsed_ms": int((time.time() - started_at) * 1000),
                },
                ensure_ascii=False,
                indent=2,
            )

        if action_clean == "list":
            doc = _load_space_document(target_space)
            all_items = doc.get("items", [])
            items = all_items if include_done else [it for it in all_items if it.get("status") != "done"]
            open_count = sum(1 for it in all_items if it.get("status") == "open")
            done_count = sum(1 for it in all_items if it.get("status") == "done")

            return json.dumps(
                {
                    "ok": True,
                    "action": "list",
                    "space": target_space,
                    "total": len(all_items),
                    "open": open_count,
                    "done": done_count,
                    "items": items[:limit],
                    "elapsed_ms": int((time.time() - started_at) * 1000),
                },
                ensure_ascii=False,
                indent=2,
            )

        if action_clean == "summary":
            if space.strip():
                doc = _load_space_document(target_space)
                all_items = doc.get("items", [])
                open_count = sum(1 for it in all_items if it.get("status") == "open")
                done_count = sum(1 for it in all_items if it.get("status") == "done")
                return json.dumps(
                    {
                        "ok": True,
                        "action": "summary",
                        "scope": "space",
                        "space": target_space,
                        "total": len(all_items),
                        "open": open_count,
                        "done": done_count,
                        "elapsed_ms": int((time.time() - started_at) * 1000),
                    },
                    ensure_ascii=False,
                    indent=2,
                )

            spaces_summary = []
            total_open = 0
            total_done = 0
            for sp in _list_spaces():
                doc = _load_space_document(sp)
                all_items = doc.get("items", [])
                open_count = sum(1 for it in all_items if it.get("status") == "open")
                done_count = sum(1 for it in all_items if it.get("status") == "done")
                spaces_summary.append(
                    {
                        "space": sp,
                        "total": len(all_items),
                        "open": open_count,
                        "done": done_count,
                    }
                )
                total_open += open_count
                total_done += done_count

            return json.dumps(
                {
                    "ok": True,
                    "action": "summary",
                    "scope": "all",
                    "spaces": spaces_summary,
                    "total_open": total_open,
                    "total_done": total_done,
                    "elapsed_ms": int((time.time() - started_at) * 1000),
                },
                ensure_ascii=False,
                indent=2,
            )

        if not todo_id.strip():
            raise ValueError("todo_id is required for this action")

        lookup_space = target_space if space.strip() else None
        found_space, doc, idx = _find_todo(todo_id.strip(), space=lookup_space)
        item = doc["items"][idx]

        if action_clean == "check":
            return json.dumps(
                {
                    "ok": True,
                    "action": "check",
                    "space": found_space,
                    "item": item,
                    "is_completed": item.get("status") == "done",
                    "elapsed_ms": int((time.time() - started_at) * 1000),
                },
                ensure_ascii=False,
                indent=2,
            )

        now = _utc_now_iso()

        if action_clean == "complete":
            item["status"] = "done"
            item["completed_at"] = now
            item["updated_at"] = now
            doc["items"][idx] = item
            _save_space_document(found_space, doc)
            return json.dumps(
                {
                    "ok": True,
                    "action": "complete",
                    "space": found_space,
                    "item": item,
                    "elapsed_ms": int((time.time() - started_at) * 1000),
                },
                ensure_ascii=False,
                indent=2,
            )

        if action_clean == "reopen":
            item["status"] = "open"
            item["completed_at"] = None
            item["updated_at"] = now
            doc["items"][idx] = item
            _save_space_document(found_space, doc)
            return json.dumps(
                {
                    "ok": True,
                    "action": "reopen",
                    "space": found_space,
                    "item": item,
                    "elapsed_ms": int((time.time() - started_at) * 1000),
                },
                ensure_ascii=False,
                indent=2,
            )

        if action_clean == "update":
            touched = False
            if title.strip():
                item["title"] = title.strip()
                touched = True
            if details.strip():
                item["details"] = details.strip()
                touched = True
            if priority.strip():
                item["priority"] = priority_clean
                touched = True
            if tags.strip():
                item["tags"] = _parse_tags(tags)
                touched = True

            if not touched:
                raise ValueError("update requires at least one field: title, details, priority, or tags")

            item["updated_at"] = now
            doc["items"][idx] = item
            _save_space_document(found_space, doc)
            return json.dumps(
                {
                    "ok": True,
                    "action": "update",
                    "space": found_space,
                    "item": item,
                    "elapsed_ms": int((time.time() - started_at) * 1000),
                },
                ensure_ascii=False,
                indent=2,
            )

        if action_clean == "delete":
            removed = doc["items"].pop(idx)
            _save_space_document(found_space, doc)
            return json.dumps(
                {
                    "ok": True,
                    "action": "delete",
                    "space": found_space,
                    "removed": removed,
                    "elapsed_ms": int((time.time() - started_at) * 1000),
                },
                ensure_ascii=False,
                indent=2,
            )

    raise RuntimeError("unexpected todos state")


mcp_app = mcp.http_app(transport="streamable-http")
app = APIKeyProtectedApp(mcp_app)

if __name__ == "__main__":
    print(f"Todos MCP Server starting on http://{HOST}:{PORT}/mcp (streamable-http)", flush=True)
    print(f"Config file: {config_path}", flush=True)
    print(f"Todos storage directory: {TODOS_STORAGE_DIR}", flush=True)
    print(f"Max items per space: {TODOS_MAX_ITEMS_PER_SPACE}", flush=True)
    print(f"Debug level: {list(LOG_LEVELS.keys())[DEBUG_LEVEL]}", flush=True)
    sys.stdout.flush()

    uvicorn.run(app, host=HOST, port=PORT)
