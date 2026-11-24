# Control Development

## Source layout

- Services are in `src/` and mounted into container at `/app`.
- Config is in `config/` and mounted at `/config`.
- Changes to Python usually require container restart (or reload where supported).

## Tests and scripts

- `src/test/`: Python tests for video, MCP, TTS, web API.
- Existing shell tests under `onboard/src/streamer/tests/` for streamer health/snapshot.

## Adding a persona

1. Create `config/agents/<Name>/` with config, prompts, SOUL, assets.
2. Set `config/selected`.
3. Restart control.

## Adding a tool

1. Create descriptor in `config/tools/<name>.yaml`.
2. Ensure MCP endpoint reachable.
3. Add stem to agent `[tools].list`.
4. Restart agent.

## Adding a skill

1. Create `config/skills/<name>.md` with frontmatter and required tools.
2. Add stem to agent `[skills].list`.

## Adding a web app

Follow Flask + SocketIO pattern in `src/web_*.py`, assign port, add Caddy route, launch in `docker-entrypoint.sh`.

## Logging

- Agent logs: `log/agent_YYYY-MM-DD.log` and console.
- Supervisord stdout/stderr: container logs.