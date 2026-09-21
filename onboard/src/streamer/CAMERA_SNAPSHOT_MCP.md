# Camera Snapshot MCP

SSE-based MCP service for taking real-time camera snapshots as base64 data URLs.

## What it solves

- Exposes a simple MCP tool to capture a fresh camera frame on demand
- Returns image content as a base64 JPEG data URL for direct model/tool consumption
- Uses the same camera pipeline as the streamer service, including fallback snapshot mode
- Avoids blocking the async server loop by running camera capture and JPEG encoding in worker threads

## Service

- Container/service: `onboard`
- Endpoint (host): `http://<host>:8000/mcp`
- Endpoint (internal): `http://onboard:8000/mcp`
- Transport: `sse`
- MCP server name: `CameraManager`
- MCP tool name: `camera_snapshot`

SSE connection paths:

- Handshake stream: `/mcp/sse`
- RPC messages: `/mcp/messages/?session_id=<id>`

## Config

Config file example: `onboard/src/streamer/config.example.toml`

```toml
[server]
host = "0.0.0.0"
port = 8000

[camera]
device = "/dev/video0"
width = 640
height = 480
fps = 30
format = "yuyv422"

[snapshot]
format = "jpeg"
quality = 80
timeout_seconds = 2.0
width = 640
height = 480
```

## Tool arguments

- `camera_snapshot`: no arguments

## Tool return format

- Success: `data:image/jpeg;base64,<...>`
- Failure: `Error: Camera not available`

## Example MCP call

```json
{"name":"camera_snapshot","arguments":{}}
```

## Runtime notes

- The MCP app is mounted at `/mcp` inside the FastAPI service running on port `8000`.
- Snapshot capture uses `streamer.snapshot(cfg, 2.0)` and then JPEG-encodes with quality `85` for MCP responses.
- This MCP service currently does not enforce API-key authentication in `app/main.py`.
- The same service also exposes non-MCP HTTP endpoints: `/start_stream`, `/stop_stream`, `/snapshot`, and `/health`.
