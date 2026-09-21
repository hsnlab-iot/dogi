# Vision Prompt MCP

Standalone Streamable HTTP MCP service for camera snapshot prompting.

## What it solves

- Captures a fresh image from snapshot endpoint
- Sends prompt + image to vision model via OpenAI-compatible API
- Supports short, medium, long response length modes
- Optionally emits snapshot to Socket.IO for UI telemetry

## Service

- Container: `cloud-mcp`
- Public endpoint via MCP Caddy: `http://<host>:5060/mcp/vision`
- Internal endpoint: `http://dogi-mcp:5000/mcp`
- MCP tool name: `vision_prompt`

## Config

Config file: `mcp/vision_prompt_config.toml`

```toml
[server]
host = "0.0.0.0"
port = 5000
http_timeout_seconds = 15

[logging]
level = "DEBUG"

[snapshot]
url = "http://dogi:5051/jpeg"

[openai]
base_url = "http://10.6.6.20:11434/v1"
model = "qwen3-vl:4b"
timeout_seconds = 30
image_input_mode = "base64"
image_detail = "auto"
max_tokens = 2048
temperature = 0.0
enable_thinking = false

[answer_lengths]
short = 256
medium = 512
long = 2048
```

## Tool arguments

- `prompt` (required): prompt for the vision model
- `answer_length` (optional): `short` | `medium` | `long`

## Example call

```json
{"prompt":"What do you see in front of the robot?","answer_length":"short"}
```

## Runtime notes

- Set `MCP_KEY` for API key authentication
- Set `VISION_PROMPT_CONFIG` to load config path
- Uses OpenAI key from `OPENAI_KEY` (defaults to `not-needed`)
