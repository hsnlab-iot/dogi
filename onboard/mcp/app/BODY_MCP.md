# Body MCP

Standalone Streamable HTTP MCP service for DOGZILLA body motion and posture control.

## What it solves

- Exposes safe, structured robot body controls as MCP tools
- Handles chassis movement (step, turn, stop) with pace and duration caps
- Supports in-place body attitude control (twist/tilt/reset) without walking
- Triggers predefined full-body action routines (sit, wave, dance, crawl, stretch, and more)
- Enforces API key authentication for all `/mcp` HTTP requests

## Service

- Container: `onboard-mcp`
- Endpoint (host): `http://<host>:5000/mcp`
- Endpoint (internal): `http://onboard-mcp:5000/mcp`
- Transport: `streamable-http`
- MCP server name: `dogzilla`

## Runtime and config

Configuration is environment-variable driven:

- `MCP_KEY` (required): API key expected by the MCP server
- `MCP_HOST` (optional, default: `0.0.0.0`): bind address
- `MCP_PORT` (optional, default: `5000`): Body MCP port
- `DOGZILLA_API_BASE` (compose-set): upstream robot API base URL used by DOGZILLA client stack

Auth headers accepted:

- `x-api-key: <MCP_KEY>`
- `Authorization: Bearer <MCP_KEY>`

## Tools

### `body_move`

Low-level locomotion and turning.

Arguments:

- `action` (required): `step` | `turn` | `stop`
- `direction` (required for `step` and `turn`): `forward` | `back` | `left` | `right`
- `steps` (optional, default `15`): used by `step`
- `duration` (optional, default `1.0`, max `3.0`): movement duration cap in seconds
- `pace` (optional, default `normal`): `slow` | `normal` | `high`

Notes:

- `stop` ignores direction/steps and halts immediately.
- After a moving command, the server auto-stops after the duration cap.

### `body_attitude`

In-place torso attitude control; feet stay planted.

Arguments:

- `action` (required): `twist` | `tilt` | `reset_attitude`
- `direction` (required for `twist`/`tilt`): `left` | `right` | `up` | `down`
- `amount` (optional, default `8`, max `20`): attitude magnitude

Behavior:

- `twist` adjusts yaw
- `tilt` adjusts pitch
- `reset_attitude` resets yaw/pitch/roll to centered values

### `body_action`

Predefined high-level action routines.

Argument:

- `action` (required), supported values:
	- `sit`, `wave`, `dance`, `happy`, `handshake`, `spin`, `stretch`, `shake_head`, `pee`, `squat`, `crawl`, `march`, `three_squats`, `seesaw`, `sway`, `full_dance`, `swing`, `fancy_stretch`, `head_circle`, `body_circle`, `nod`

## Example calls

```json
{"tool":"body_move","arguments":{"action":"step","direction":"forward","steps":20,"duration":1.5,"pace":"normal"}}
```

```json
{"tool":"body_attitude","arguments":{"action":"tilt","direction":"up","amount":10}}
```

```json
{"tool":"body_action","arguments":{"action":"wave"}}
```

## Runtime notes

- Server starts with Uvicorn and mounts FastMCP HTTP app at `/mcp`.
- If `MCP_KEY` is missing, server startup fails intentionally.
- Invalid or missing API key on `/mcp` requests returns `401` with `{"detail":"Invalid API key"}`.
- The container entrypoint launches Body MCP and Memory MCP in a tmux session.
