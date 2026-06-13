# academic-workflow-mcp

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)

An [MCP](https://modelcontextprotocol.io) server that connects **Zotero** and **Obsidian** into a streamlined AI-assisted academic reading workflow — compatible with Claude Code, Codex, OpenClaw, Cursor, and any other MCP client.

> **中文简介：** 将 Zotero（文献管理）与 Obsidian（知识库）连接为统一的 AI 辅助科研精读工作流。支持批量导入 PDF、自动提取标题、查重检测、双向删除同步，以及完整的精读笔记生成与归档流程。

---

## ✨ What it does

| Step | Tool | Description |
|------|------|-------------|
| 0. Import | `workflow_import_pdfs` | Batch-import PDFs into Zotero with title extraction and deduplication |
| 0. Dedupe | `workflow_find_duplicates` | Scan for duplicate Zotero items by identical DOI or similar title |
| 1. Fetch | `workflow_get_paper` | Pull metadata + full text + annotations from Zotero in one call |
| 2. Write | `workflow_write_note` | Create a structured Obsidian note with YAML frontmatter |
| 3. Link | `workflow_attach_zotero_note` | Add a short summary note under the Zotero item with a back-link |
| 4. Sync | `workflow_sync_highlights` | Propagate PDF highlights (by color category) into the Obsidian note |
| 5. Archive | `workflow_confirm_review` | After human review — update status in Obsidian + tags in Zotero |
| + | `workflow_list_papers` | List papers by tag/collection, optionally cross-checking Obsidian |
| + | `workflow_get_note` | Read an existing Obsidian literature note |
| + | `workflow_sync_check` | Bidirectional deletion sync — clean up orphan notes and trashed items |

The AI handles **analysis and writing**; the MCP server handles **plumbing** (API calls, file I/O, format consistency).

---

## 🛠 Prerequisites

| Requirement | Notes |
|-------------|-------|
| Python 3.10+ | Required by the MCP SDK |
| [Zotero 7+](https://www.zotero.org/) desktop app | Must be running; local API on port 23119 |
| [Better BibTeX](https://retorque.re/zotero-better-bibtex/) plugin for Zotero | Generates stable citekeys used as universal IDs |
| [Obsidian](https://obsidian.md/) desktop app | Must be running |
| [Local REST API](https://github.com/coddingtonbear/obsidian-local-rest-api) Obsidian plugin | Exposes vault API on port 27123 |
| Zotero Web API key | For write operations (tags, child notes). Get one at [zotero.org/settings/keys](https://www.zotero.org/settings/keys) |

---

## 🚀 Installation

### Option A — pip from GitHub (recommended)

```bash
pip install git+https://github.com/wuruiqi/academic-workflow-mcp.git
```

This installs an `academic-workflow-mcp` command that starts the stdio MCP server.

### Option B — uvx (no install)

```bash
uvx --from git+https://github.com/wuruiqi/academic-workflow-mcp.git academic-workflow-mcp
```

### Option C — clone and run

```bash
git clone https://github.com/wuruiqi/academic-workflow-mcp.git
cd academic-workflow-mcp
pip install -e .
cp .env.example .env    # fill in your keys
```

---

## ⚙️ Configuration

Copy `.env.example` to `.env` and fill in your values:

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `OBSIDIAN_API_KEY` | — | ✅ | Key from the Local REST API plugin settings |
| `OBSIDIAN_URL` | `http://127.0.0.1:27123` | | Obsidian REST API base URL |
| `OBSIDIAN_VAULT_NAME` | — | | Vault name for `obsidian://` deep-links |
| `LITERATURE_FOLDER` | `10-Literature` | | Vault folder for literature notes |
| `ZOTERO_LOCAL_URL` | `http://127.0.0.1:23119` | | Zotero local connector URL |
| `ZOTERO_API_KEY` | — | for writes | Zotero Web API key |
| `ZOTERO_LIBRARY_ID` | — | for writes | Numeric library ID (shown at zotero.org/settings/keys) |
| `ZOTERO_LIBRARY_TYPE` | `user` | | `user` or `group` |
| `ZOTERO_DATA_DIR` | — | for PDF import | Path to your Zotero data directory (e.g. `C:\Users\you\Zotero`) |

---

## 🔌 Register with your MCP client

### Claude Code / Claude Desktop

```json
{
  "mcpServers": {
    "academic-workflow": {
      "command": "academic-workflow-mcp",
      "env": {
        "OBSIDIAN_API_KEY": "your_key",
        "OBSIDIAN_VAULT_NAME": "Research",
        "ZOTERO_API_KEY": "your_key",
        "ZOTERO_LIBRARY_ID": "12345678",
        "ZOTERO_DATA_DIR": "C:\\Users\\you\\Zotero"
      }
    }
  }
}
```

### Codex / OpenClaw / Cursor (any stdio MCP client)

```json
{
  "mcpServers": {
    "academic-workflow": {
      "type": "stdio",
      "command": "academic-workflow-mcp"
    }
  }
}
```

Or with uvx (no pre-install):

```json
{
  "mcpServers": {
    "academic-workflow": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/wuruiqi/academic-workflow-mcp.git",
        "academic-workflow-mcp"
      ]
    }
  }
}
```

---

## 📖 Typical workflow

```
# 0. Batch-import a folder of PDFs you just downloaded:
"Import all PDFs in D:/papers/slam/ into Zotero collection '1_SLAM'"

# The AI calls:
workflow_import_pdfs(["D:/papers/slam/wang2024.pdf", ...], collection="1_SLAM")
  → imports PDFs, extracts real titles, warns on filename/content mismatches,
    skips files already in Zotero

# 0b. Check for duplicates after import:
"Find duplicate papers in my SLAM collection"

workflow_find_duplicates(collections=["1_SLAM"])
  → returns groups of items sharing a DOI or a highly similar title

# 1. Ask your AI assistant:
"Read and annotate the paper with citekey wang2024deep"

# The AI will call:
workflow_get_paper("wang2024deep")
  → returns metadata, full text, annotations

# Then generate the note content and call:
workflow_write_note(citekey, metadata, sections)
  → creates 10-Literature/wang2024deep.md in Obsidian

workflow_attach_zotero_note(item_key, citekey, summary)
  → adds a summary note under the Zotero item

# 2. You review the note in Obsidian, then tell the AI:
"wang2024deep confirmed, mark as reviewed"

# The AI calls:
workflow_confirm_review("wang2024deep", item_key)
  → Obsidian: status → reviewed
  → Zotero: #在读 → #已精读

# 3. Later, after highlighting the PDF in Zotero:
"Sync my highlights for wang2024deep"

workflow_sync_highlights("wang2024deep", item_key)
  → appends color-categorized highlights to the note

# 4. Periodically clean up after deleting papers in Zotero:
"Check if any Obsidian notes need to be cleaned up after my recent Zotero deletions"

workflow_sync_check(direction="both")
  → dry-run report of orphan notes and ghost items

workflow_sync_check(direction="both", auto_apply=True)
  → actually deletes orphan Obsidian notes and trashes ghost Zotero items
```

---

## 🗂 Note structure

Literature notes follow a bilingual heading convention so the LLM can
fill sections regardless of the user's language:

```markdown
---
citekey: "wang2024deep"
title: "..."
authors: [Wang, X., Li, Y.]
year: 2024
journal: "IEEE TPAMI"
doi: "10.1109/..."
zotero: "zotero://select/library/items/XXXXXXXX"
tags: [literature]
rating: ⭐⭐⭐
status: pending-review
---

## One-line Summary / 一句话总结
## Research Question & Motivation / 研究问题与动机
## Methods / 方法
## Key Results / 主要结果
## Contributions / 创新点
## Limitations & Open Questions / 局限与可质疑之处
## Relevance to My Research / 与我课题的关系
## Highlights from Paper / 关键引文摘录
## Further Reading / 延伸阅读
```

Highlights are grouped by annotation color:

| Color | Category |
|-------|----------|
| 🟡 Yellow | Key Point |
| 🔴 Red | Critical / Question |
| 🟢 Green | Method / Technique |
| 🔵 Blue | Data / Result |
| 🟣 Purple | Background |

---

## 🧰 MCP tools reference

### `workflow_import_pdfs(pdf_paths, collection="", item_type="preprint")`
Batch-import PDF files into Zotero with automatic title extraction and smart deduplication.

- Extracts the real title from PDF metadata or largest-font first-page text (not just the filename).
- Detects **title mismatches** between the filename and PDF content — useful for catching mislabeled downloads.
- **Smart dedup**: if an identical file already has a PDF in Zotero → skip; if a metadata-only entry exists with no PDF → attach PDF to it rather than creating a duplicate.
- Copies the PDF into `<zotero_data_dir>/storage/` so Zotero can open it immediately.

Returns `imported`, `skipped`, `failed`, and `warnings` (title mismatches) lists.

### `workflow_find_duplicates(collections=[], title_threshold=0.85)`
Scan Zotero for duplicate items grouped by identical DOI or highly similar title.

- `collections`: collection names to scan; leave empty to scan the entire library.
- `title_threshold`: word-overlap ratio (default 0.85). Lower to catch more near-duplicates.

Returns grouped duplicate sets with a `suggested_keep` item key for each group.

### `workflow_get_paper(identifier)`
Retrieve metadata, full text, and annotations from Zotero by citekey, item key, DOI, or title.

### `workflow_write_note(citekey, metadata, sections, overwrite=False)`
Write a structured literature note to `10-Literature/<citekey>.md` with `status: pending-review`.

### `workflow_attach_zotero_note(item_key, citekey, summary, rating, cite_in)`
Create a short child note under the Zotero item with an `obsidian://` back-link.

### `workflow_sync_highlights(citekey, item_key)`
Pull PDF annotations from Zotero and update the highlights section of the Obsidian note.

### `workflow_confirm_review(citekey, item_key, tag_remove, tag_add)`
Mark a note as reviewed: `status → reviewed` in Obsidian, tag update in Zotero.

### `workflow_list_papers(tag, collection, limit, check_notes)`
List Zotero papers filtered by tag or collection, with optional Obsidian note status.

### `workflow_get_note(citekey)`
Read the current content of a literature note from Obsidian.

### `workflow_sync_check(direction="both", auto_apply=False)`
Bidirectional deletion sync between Zotero and Obsidian.

- **`"trash_to_obs"`**: finds Obsidian notes whose Zotero item is now in the trash.
- **`"obs_to_zotero"`**: finds orphan Obsidian notes (Zotero item deleted) and Zotero items whose linked Obsidian note was removed.
- **`"both"`**: runs both directions.
- Default `auto_apply=False` is a dry run — review the report before passing `True`.

---

## 🛠 Development

```bash
git clone https://github.com/wuruiqi/academic-workflow-mcp.git
cd academic-workflow-mcp
pip install -e ".[dev]"
cp .env.example .env
python -m pytest tests/ -m "not integration"
```

Integration tests (`-m integration`) require Zotero and Obsidian to be running.

---

## 📋 Changelog

### v0.2.0
- **New**: `workflow_import_pdfs` — batch PDF import with real-title extraction, filename/content mismatch detection, and smart deduplication
- **New**: `workflow_find_duplicates` — scan Zotero for duplicate items by DOI or similar title
- **New**: `workflow_sync_check` — bidirectional deletion sync: clean orphan Obsidian notes when Zotero items are trashed, and vice versa
- **Config**: added `ZOTERO_DATA_DIR` env variable for PDF storage during import

### v0.1.0
- Initial release: `workflow_get_paper`, `workflow_write_note`, `workflow_attach_zotero_note`, `workflow_sync_highlights`, `workflow_confirm_review`, `workflow_list_papers`, `workflow_get_note`

---

## License

[MIT](LICENSE) © wuruiqi
