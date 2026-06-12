# academic-workflow-mcp

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)

An [MCP](https://modelcontextprotocol.io) server that connects **Zotero** and **Obsidian** into a streamlined AI-assisted academic reading workflow — compatible with Claude Code, Codex, OpenClaw, Cursor, and any other MCP client.

> **中文简介：** 将 Zotero（文献管理）与 Obsidian（知识库）连接为统一的 AI 辅助科研精读工作流。一次调用即可完成取材、精读笔记生成、高亮同步与归档确认。

---

## ✨ What it does

| Step | Tool | Description |
|------|------|-------------|
| 1. Fetch | `workflow_get_paper` | Pull metadata + full text + annotations from Zotero in one call |
| 2. Write | `workflow_write_note` | Create a structured Obsidian note with YAML frontmatter |
| 3. Link | `workflow_attach_zotero_note` | Add a short summary note under the Zotero item with a back-link |
| 4. Sync | `workflow_sync_highlights` | Propagate PDF highlights (by color category) into the Obsidian note |
| 5. Archive | `workflow_confirm_review` | After human review — update status in Obsidian + tags in Zotero |
| + | `workflow_list_papers` | List papers by tag/collection, optionally cross-checking Obsidian |
| + | `workflow_get_note` | Read an existing Obsidian literature note |

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
        "ZOTERO_LIBRARY_ID": "12345678"
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

## License

[MIT](LICENSE) © wuruiqi
