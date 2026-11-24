# Control Architecture

## Runtime model

The control plane runs as one main container (`dogi`) with multiple Python services managed by supervisord/tmux, plus separate MCP and support containers.

**Caddy is a key part of the architecture**: internal apps run on separate ports, but Caddy exposes them through a **single external port** (5059) using path-based routing. This keeps the browser-facing surface simple while allowing many internal services.

```text
Browser
  -> Caddy :5059 (single entry point)
       -> /apps/system/*  -> Flask :5050
       -> /video/*        -> Flask :5051
       -> /apps/search/*  -> Flask :5053
       -> ... (other apps :5052-:5058)
       -> /*             -> Main UI :5059
  -> Agent :5058 -> LLM provider
  -> MCP tools -> Onboard services / cloud MCP
```

## Services and ports

| Port | Service | File |
|---|---|---|
| 5050 | System UI | `src/web_system.py` |
| 5051 | Video stream | `src/web_video.py` |
| 5052 | Voice | `src/web_voice.py` |
| 5053 | Keresd (search game) | `src/web_keresd.py` |
| 5054 | Mutasd (show) | `src/web_mutasd.py` |
| 5055 | Kovesd (follow) | `src/web_kovesd.py` |
| 5056 | Prompt | `src/web_prompt.py` |
| 5057 | Pupality | `src/web_pupality.py` |
| 5058 | Agent | `src/agent.py` / `src/web_agent.py` |
| 5059 | Main UI / status API | `src/web_main.py` |

Other control-plane ports:

- 5002/UDP: `DOGZILLAProxyServer.py` (robot action proxy client side)
- 5010/TCP, 5011/TCP: TTS service
- 5100/UDP: incoming H.264 video
- `/tmp/video_frames_*.ipc`: ZMQ frame channels

## Agent flow

1. UI sends prompt via Socket.IO to agent.
2. Agent builds Pydantic AI agent with configured LLM and MCP toolsets.
3. Toolsets are probed at startup; unavailable endpoints are skipped.
4. Agent executes tool calls (body, vision, capture, todos, etc.).
5. Responses, tool events, and stats are emitted to UI.
6. Optional TTS speaks final response.

## Video pipeline (control side)

- UDP video arrives on 5100.
- `zmq_videopub.py` publishes to `/tmp/video_frames_c.ipc`.
- Processing apps (`keresd.py`, `kovesd.py`, `mutasd.py`) consume/publish their own IPC channels.
- `web_video.py` serves MJPEG to browsers.

## MCP integration

Cloud MCP endpoints:

- Vision prompt MCP: internal 5000, public via Caddy MCP proxy 5060 `/mcp/vision`
- Todos MCP: internal 5001, public via Caddy MCP proxy 5060 `/mcp/todos`

Like the web proxy, the MCP proxy keeps multiple internal MCP services behind one external port.

Onboard MCP endpoints are referenced by tool descriptors (e.g. body, capture) and probed at runtime.

## Speech-to-text

STT is browser-based and coordinated via Ably Realtime. `prompt.py` receives recognized text and forwards it to prompt pipeline. See [stt.md](stt.md).