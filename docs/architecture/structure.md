# Project Structure

```
academic-workflow-mcp/
├── server.py              # FastMCP entry point; all 10 @mcp.tool() definitions
├── workflow/
│   ├── zotero.py          # Zotero local API (port 23119) + Web API; PDF import helpers
│   ├── obsidian.py        # Obsidian Local REST API (port 27123); note CRUD
│   ├── templates.py       # Note skeleton builder, annotation formatter
│   └── __init__.py
├── tests/
│   ├── test_unit.py       # Unit tests (no live services)
│   └── test_connection.py # Integration tests (require Zotero + Obsidian)
├── pyproject.toml         # Package metadata; entry-point: academic-workflow-mcp → server:main
├── AGENT.md               # AI tool quick-start (architecture, tools, env vars)
└── docs/                  # This directory
```

## Core File Responsibilities

| File | Responsibility |
|------|----------------|
| `server.py` | All MCP tool definitions (`@mcp.tool()`); no business logic |
| `workflow/zotero.py` | All Zotero communication; PDF import; dedup logic |
| `workflow/obsidian.py` | All Obsidian communication; note CRUD; frontmatter patching |
| `workflow/templates.py` | Note formatting; annotation color mapping |
