# Runtime Skills

Skill format: Agent Skills Open Standard (Markdown + Frontmatter).

Each skill is a single Markdown file under this folder.

In agent config files, reference skills without extension:

```toml
[skills]
list = ["sql-optimization-skill"]
```

Expected skill file path for the example above:
- `config/skills/sql-optimization-skill.md`

Skill file structure:

```md
---
id: sql-optimization-skill
name: SQL Query Optimizer
description: Guide for complex SQL optimization.
required_mcp_tools:
	- postgres-mcp-server/execute_query
	- postgres-mcp-server/explain_analyze
tags: [database, performance]
version: 1.2.0
---

# SQL Optimization Workflow
...
```

Runtime behavior:
- Skills are included in system prompt only if all `required_mcp_tools` are available.
- Required entries can match tool capabilities from:
	- `provided_mcp_tools`
	- tool `tags`
	- tool logical `name`
- Missing dependencies cause the skill to be skipped.
