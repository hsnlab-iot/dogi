# Control Deployment

## Compose stack

File: `cloud/control/docker-compose.yaml`.

Services:

- `dogi-base` (profile `base`): base image build.
- `control` (`dogi`): main control container.
- `cloud-mcp` (`dogi-mcp`): vision + todos MCP.
- `opentts`: TTS service.
- `victoriametrics`: metrics storage.
- `phoenix`: tracing UI.
- `caddy`: web proxy on 5059.
- `caddy-mcp`: MCP proxy on 5060.

Startup:

```bash
cd cloud/control
cp .env.sample .env  # fill secrets
docker compose up -d --build
```

## Environment

`.env` / compose provide:

- `MCP_KEY`
- `ABLY_USER_KEY`, `ABLY_MASTER_KEY`, `ABLY_ROOM_ID`
- `GEMINI_API_KEY` (if used)
- `ROBOT_IP`
- `DOGZILLA_API_BASE`
- `VICTORIA_BASE_URL`
- `PHOENIX_COLLECTOR_ENDPOINT`

## Ports

| Port | Service |
|---|---|
| 5059 | Caddy web proxy (main UI) |
| 5060 | Caddy MCP proxy |
| 5500 | OpenTTS |
| 6006 | Phoenix UI |
| 4317 | Phoenix OTLP gRPC |
| 8428 | VictoriaMetrics |

## Volumes

- `src/` -> `/app` (read-only)
- `config/` -> `/config`
- `cache/`, `log/`, `storage/` persisted
- MCP configs and todos data mounted into `cloud-mcp`

## GPU

`control` and `opentts` reserve NVIDIA GPU.