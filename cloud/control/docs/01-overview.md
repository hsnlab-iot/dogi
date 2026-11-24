# Control Plane Overview

`cloud/control` is the **cloud-side brain and UI** for DOGI. It runs on the GPU/control workstation and connects to onboard robot services over the network.

## Responsibilities

- Serve web applications for operators and games.
- Run the AI agent (Pydantic AI) with configured LLM and MCP tools.
- Proxy and coordinate robot commands.
- Handle video ingestion/display and stream monitoring.
- Provide voice (STT/TTS) integration.
- Manage configurable AI personas ("pupalities").
- Expose MCP services (current examples include task tracking and vision; more can be added).
- Collect telemetry and logs.

## Main capabilities

- Flask/SocketIO web apps on ports 5050-5059 (the set can be extended).
- Agent console with tool calls and stats.
- Camera stream viewing and snapshot access.
- Voice and speech-to-text (browser-based, Ably-coordinated).
- Persona management and switching.
- MCP tool orchestration: body motion, camera snapshot, vision, todos (examples; extensible).
- Metrics (VictoriaMetrics) and tracing (Phoenix).

## Directory layout (`cloud/control`)

| Path | Purpose |
|---|---|
| `src/` | Python services, web apps, agent, utils. |
| `config/` | Agents, tool descriptors, skills, selected persona. |
| `mcp/` | Cloud MCP servers and configs. |
| `docs/` | Control documentation (this folder). |
| `storage/`, `cache/`, `log/` | Runtime data, caches, logs. |
| `Caddyfile`, `Caddyfile.mcp` | Reverse proxy configs. |
| `docker-compose.yaml` | Control stack. |
| `Dockerfile`, `Dockerfile.base` | Images. |

## Key concepts

- **Agent/pupality**: configured persona with model, tools, skills, language, TTS.
- **Tool descriptor**: file describing one MCP endpoint.
- **Skill**: Markdown guidance injected when dependencies are available.
- **STT**: browser speech recognition coordinated by Ably; see `stt.md`.