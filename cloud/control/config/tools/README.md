# MCP Tool Descriptors

Each file in this folder describes one MCP server endpoint.

Supported file formats:
- `.yaml` / `.yml` (recommended)
- `.json`
- `.toml`

Required fields:
- `type`: one of `ssh`, `sse`, `str`
- `url`: connection target

Optional fields:
- `name`: logical tool name
- `description`: short human-readable description
- `tags`: list of tags/capabilities
- `provided_mcp_tools`: explicit MCP capability ids (`server/tool`)
- `source_file`: local source file used for capability/tag inference

In agent config files, reference tool descriptors without extension:

```toml
[tools]
list = ["highfive", "dice"]
```

## YAML example

```yaml
name: visionprompt
type: str
url: http://dogi-mcp:5000/mcp
description: Vision prompt MCP server
provided_mcp_tools:
  - visionprompt/vision_prompt
tags:
  - vision
  - image
  - analysis
```

## JSON example

```json
{
  "name": "visionprompt",
  "type": "str",
  "url": "http://dogi-mcp:5000/mcp",
  "description": "Vision prompt MCP server"
}
```

## TOML example

```toml
name = "capture"
type = "sse"
url = "http://robot_ip:8000/mcp/sse"
description = "Camera capture MCP server"
```

## YAML example

```yaml
name: highfive
type: ssh
url: robot@10.6.6.20:~/kutyus_env/bin:~/mcptest/server.py
description: Highfive MCP server
```
