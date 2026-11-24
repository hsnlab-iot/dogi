# DOGI Control Documentation

Documentation for the **cloud control plane** (`cloud/control`): the web UIs, AI agent, configuration, MCP integrations, and deployment of the DOGI robot control system.

This is **iteration 1 (top level)** for the control component. Deeper per-module docs can follow after review.

## Index

- [01-overview.md](01-overview.md) — what the control plane does
- [02-architecture.md](02-architecture.md) — runtime flow and services
- [03-components.md](03-components.md) — source files and responsibilities
- [04-deployment.md](04-deployment.md) — compose, env, ports, volumes
- [05-configuration.md](05-configuration.md) — agents, tools, skills, prompts
- [06-development.md](06-development.md) — extending and debugging control
- [07-glossary.md](07-glossary.md) — control-specific terms
- [stt.md](stt.md) — speech-to-text concept and implementation

## Existing component docs

- `src/README.md` — web server/service port map
- `config/tools/README.md` — MCP tool descriptor format
- `config/skills/README.md` — runtime skill format
- `mcp/TODOS_MCP.md`, `mcp/VISION_PROMPT_MCP.md` — cloud MCP services

## Scope note

This documentation covers only `cloud/control`. Onboard robot services, RealSense streaming, and base images are documented separately in their own folders.