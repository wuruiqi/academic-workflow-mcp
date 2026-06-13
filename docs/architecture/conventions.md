# Development Conventions

## Tool definition pattern

All tools are defined in `server.py` using `@mcp.tool()`. Business logic lives in `workflow/` modules. Tools should not contain logic beyond argument validation and delegation.

## Identifier resolution

`workflow_get_paper` accepts: 8-char item key, Better BibTeX citekey, DOI, or title keywords. Prefer exact citekey match when multiple results returned.

## Dry-run default

`workflow_sync_check` is always a dry run unless `auto_apply=True`. Destructive tools must default to safe.

## Internal API usage

`zotero._local()` is an internal helper. Direct calls from `server.py` are acceptable but mark them with a comment if the dependency is non-obvious.

## Decisions

- **AGENT.md over CLAUDE.md in repo**: MCP targets multiple AI tools; CLAUDE.md is Claude-specific branding (2026-06-13)
- **pdfminer for title extraction**: fallback chain is metadata → largest-font text → filename stem (2026-06-13)
