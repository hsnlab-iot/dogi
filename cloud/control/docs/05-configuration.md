# Control Configuration

## Agent selection

`config/selected` contains active agent folder name. `config.init()` reads it at startup.

## Agent directory

`config/agents/<name>/`:

- `config.toml`: model provider, language, tools, skills, ports, streamer, TTS.
- `prompts.toml`: localized prompt templates.
- `SOUL.<lang>.md`: persona identity and behavior rules.
- assets (images/audio).

## Config sections

- `[pupcard]`, `[general]`, `[language]`
- `[models]`, `[llm]`, `[openai]`, `[tts]`
- `[ports]`, `[streamer]`
- `[tools]`: list of tool descriptor refs
- `[skills]`: list of skill refs

## Tool descriptors

`config/tools/*.yaml|json|toml`. Required: `type` (`ssh`, `sse`, `str`) and `url`. Optional metadata, tags, provided tools, source file.

## Skills

`config/skills/*.md` with YAML frontmatter. Included only when required MCP tools are available.

## Prompts

`prompts.toml` localized templates keyed by section/app.

## Streamer config

Onboard streamer TOML config controls camera device, resolution, FPS, snapshot quality. See `onboard/src/streamer/README.md`.