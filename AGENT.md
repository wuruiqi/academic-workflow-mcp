# academic-workflow-mcp — Agent Overview

MCP server bridging **Zotero** and **Obsidian** for AI-assisted academic reading workflows.
Compatible with Claude Code, Codex, OpenClaw, Cursor, and any stdio MCP client.

## Architecture

```
server.py          # FastMCP entry point — all 10 @mcp.tool() definitions live here
workflow/
  zotero.py        # Zotero local API (port 23119) + Web API client; PDF import helpers
  obsidian.py      # Obsidian Local REST API (port 27123) client; note CRUD
  templates.py     # Note skeleton builder, annotation formatter, Zotero child-note template
  __init__.py      # Re-exports zotero, obsidian, templates
tests/
  test_unit.py     # Unit tests (no live services needed)
  test_connection.py  # Integration tests (require Zotero + Obsidian running)
pyproject.toml     # Package metadata, version, entry-point: academic-workflow-mcp → server:main
.env.example       # Config template
```

## Tools (v0.2.0)

| # | Tool | What it does |
|---|------|--------------|
| 0 | `workflow_import_pdfs(pdf_paths, collection, item_type)` | Batch import PDFs: extract real title, detect filename mismatches, smart dedup, copy to Zotero storage |
| 1 | `workflow_find_duplicates(collections, title_threshold)` | Find duplicate Zotero items by identical DOI or similar title |
| 2 | `workflow_get_paper(identifier)` | Fetch metadata + full text + annotations from Zotero (citekey / item key / DOI / title) |
| 3 | `workflow_write_note(citekey, metadata, sections, overwrite)` | Write structured literature note to Obsidian |
| 4 | `workflow_attach_zotero_note(item_key, citekey, summary, rating, cite_in)` | Create Zotero child note with obsidian:// back-link |
| 5 | `workflow_sync_highlights(citekey, item_key)` | Sync PDF annotations from Zotero into Obsidian note |
| 6 | `workflow_confirm_review(citekey, item_key, tag_remove, tag_add)` | Mark note reviewed in Obsidian + update Zotero tags |
| 7 | `workflow_list_papers(tag, collection, limit, check_notes)` | List Zotero papers, optionally cross-check Obsidian note status |
| 8 | `workflow_get_note(citekey)` | Read existing Obsidian literature note |
| 9 | `workflow_sync_check(direction, auto_apply)` | Bidirectional deletion sync: orphan notes ↔ trashed Zotero items |

## Key design decisions

- **Identifier flexibility**: `workflow_get_paper` accepts citekey, 8-char item key, DOI, or title keywords; prefers exact citekey match.
- **Dry-run default**: `workflow_sync_check` is always a dry run unless `auto_apply=True`.
- **Dedup logic in `workflow_import_pdfs`**: skip if PDF hash already in Zotero; attach-to-stub if metadata-only entry exists.
- **Title extraction order**: PDF `Title` metadata field → largest-font text on page 1 → filename stem.

## Environment variables

| Variable | Default | Notes |
|----------|---------|-------|
| `OBSIDIAN_API_KEY` | — | Local REST API plugin key |
| `OBSIDIAN_URL` | `http://127.0.0.1:27123` | |
| `OBSIDIAN_VAULT_NAME` | — | For `obsidian://` deep-links |
| `LITERATURE_FOLDER` | `10-Literature` | Vault subfolder for notes |
| `ZOTERO_LOCAL_URL` | `http://127.0.0.1:23119` | |
| `ZOTERO_API_KEY` | — | Required for write ops |
| `ZOTERO_LIBRARY_ID` | — | Numeric; from zotero.org/settings/keys |
| `ZOTERO_LIBRARY_TYPE` | `user` | `user` or `group` |
| `ZOTERO_DATA_DIR` | — | Path to Zotero data dir; needed for PDF import storage copy |

## Dependencies

`mcp[cli]>=1.27.0`, `httpx>=0.27.0`, `python-dotenv>=1.0.0`

Python 3.10+ required (MCP SDK constraint).
