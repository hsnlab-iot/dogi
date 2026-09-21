# Todos MCP

Standalone Streamable HTTP MCP service for task tracking with date-scoped spaces.

## What it solves

- Keeps todos in a dedicated storage area (`mcp/todos_data`)
- Organizes tasks by date space (`YYYY-MM-DD`)
- Supports completion checks and task lifecycle updates
- Runs separately from vision MCP service

## Service

- Container: `cloud-mcp`
- Public endpoint via MCP Caddy: `http://<host>:5060/mcp/todos`
- Internal endpoint: `http://dogi-mcp:5001/mcp`
- MCP tool name: `todos`

## Config

Config file: `mcp/todos_config.toml`

```toml
[server]
host = "0.0.0.0"
port = 5001

[logging]
level = "INFO"

[todos]
storage_dir = "./todos_data"
max_items_per_space = 1000
```

## Tool actions

Single MCP function with `action` routing.

- `add`:
  - Required: `title`
  - Optional: `space`, `details`, `priority`, `tags`
- `list`:
  - Optional: `space`, `include_done`, `limit`
- `check`:
  - Required: `todo_id`
  - Optional: `space`
- `complete`:
  - Required: `todo_id`
  - Optional: `space`
- `reopen`:
  - Required: `todo_id`
  - Optional: `space`
- `update`:
  - Required: `todo_id`
  - Optional update fields: `title`, `details`, `priority`, `tags`
- `delete`:
  - Required: `todo_id`
  - Optional: `space`
- `summary`:
  - Optional: `space` (if omitted, returns all spaces)
- `spaces`:
  - No additional fields

## Example calls

```json
{"action":"add","title":"Calibrate lidar","space":"2026-09-14","priority":"high","tags":"robot,calibration"}
```

```json
{"action":"list","space":"2026-09-14","include_done":false}
```

```json
{"action":"complete","todo_id":"a1b2c3d4e5f6"}
```

```json
{"action":"summary"}
```

## Suggested system prompt snippet

Use this behavior policy in your dog prompt/skill:

1. At the start of each task, call `todos` with `action=add` and `space=<today YYYY-MM-DD>`.
2. Before answering progress questions, call `todos` with `action=list` and `include_done=false`.
3. When a task is finished, call `todos` with `action=complete`.
4. If requirements change, call `todos` with `action=update`.
5. At session end, call `todos` with `action=summary` for today.
