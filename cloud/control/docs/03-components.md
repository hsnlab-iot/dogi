# Control Components

## Web apps

| File | Port | Purpose |
|---|---|---|
| `src/web_system.py` | 5050 | System dashboard and controls. |
| `src/web_video.py` | 5051 | MJPEG stream endpoint. |
| `src/web_voice.py` | 5052 | Browser voice/TTS. |
| `src/web_keresd.py` | 5053 | Search game UI. |
| `src/web_mutasd.py` | 5054 | Show/scene UI. |
| `src/web_kovesd.py` | 5055 | Follow/tracking UI. |
| `src/web_prompt.py` | 5056 | Prompt entry UI. |
| `src/web_pupality.py` | 5057 | Persona management UI. |
| `src/web_agent.py` | 5058 | Agent console UI. |
| `src/web_main.py` | 5059 | Main UI, status API, ping. |

## Core services

| File | Purpose |
|---|---|
| `src/agent.py` | Pydantic AI agent, MCP toolsets, Socket.IO events. |
| `src/DOGZILLAProxyServer.py` | Robot action proxy (UDP). |
| `src/zmq_videopub.py` | Video receiver/publisher (ZMQ). |
| `src/streamer_client.py` | Starts/monitors onboard streamer. |
| `src/config.py` | Config, prompts, tools, skills loading. |
| `src/prompt.py` | Prompt pipeline. |
| `src/keresd.py`, `kovesd.py`, `mutasd.py` | Game/processing loops. |
| `src/stt_master.py`, `stt_check.py` | STT coordination. |
| `src/ollama_runtime.py`, `ollama_exporter.py` | Ollama helpers. |

## Utilities

`src/utils/`: `dogy.py`, `misc.py`, `prompt.py`, `translate.py`, `voice.py`.

## Commands

`src/commands/`: `off.py`, `sit.py`, `motoroff.py`.

## MCP

| Path | Purpose |
|---|---|
| `mcp/app/vision_prompt_mcp_server.py` | Vision prompt MCP server. |
| `mcp/app/todos_mcp_server.py` | Todos MCP server. |
| `mcp/vision_prompt_config.toml` | Vision MCP config. |
| `mcp/todos_config.toml` | Todos MCP config. |

## Configuration

- `config/agents/<name>/`: persona configs, prompts, SOUL, assets.
- `config/tools/*.yaml`: MCP tool descriptors.
- `config/skills/*.md`: runtime skills.
- `config/selected`: active persona.