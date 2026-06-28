"""
Note templates and formatting helpers.

Produces the standardized two-level note structure:
  • Obsidian deep note  — full analysis, stored in <LITERATURE_FOLDER>/<citekey>.md
  • Zotero child note   — ≤200-char summary + link back to Obsidian

Notes are deliberately project-neutral: a paper is a reusable knowledge asset,
so the deep note carries no "relevance to project X" section. Which project a
paper serves is decided later by each project owner, via tags/back-links — not
hard-coded into the note.
"""

import os
from datetime import date
from typing import Any

LITERATURE_FOLDER = os.getenv("LITERATURE_FOLDER", "0-Literature")


# ── Obsidian note ─────────────────────────────────────────────────────────────

def build_frontmatter(citekey: str, meta: dict) -> str:
    """
    Build YAML frontmatter block for a literature note.

    meta keys: title, authors (list), year, journal, doi, zotero_link
    """
    authors_yaml = ", ".join(meta.get("authors", []))
    return f"""---
citekey: "{citekey}"
title: "{meta.get('title', '').replace('"', "'")}"
authors: [{authors_yaml}]
year: {meta.get('year', '')}
journal: "{meta.get('journal', '')}"
doi: "{meta.get('doi', '')}"
zotero: "{meta.get('zotero_link', '')}"
tags: [literature]
rating: ⭐⭐⭐
status: pending-review
related: []
created: {date.today().isoformat()}
---
"""


def build_note_skeleton(citekey: str, meta: dict, sections: dict | None = None) -> str:
    """
    Build a complete Obsidian literature note.

    sections: dict mapping heading name → content string.
    Any heading not in sections is left empty with a placeholder comment.

    Standard headings (in order):
      one_line_summary, research_question, methods, results,
      contributions, limitations, highlights

    The note is project-neutral: no "relevance to project" section. Related
    papers are linked via the `related` frontmatter field ([[citekey]] links).
    """
    s = sections or {}

    def sec(heading_en: str, heading_zh: str, key: str,
            comment: str = "") -> str:
        body = s.get(key, "").strip()
        if not body and comment:
            body = f"<!-- {comment} -->"
        elif not body:
            body = ""
        return f"\n## {heading_en} / {heading_zh}\n\n{body}\n"

    return (
        build_frontmatter(citekey, meta)
        + sec("One-line Summary", "一句话总结", "one_line_summary")
        + sec("Research Question & Motivation", "研究问题与动机", "research_question")
        + sec("Methods", "方法", "methods",
              "Core approach, pipeline, difference from prior work")
        + sec("Key Results", "主要结果", "results",
              "Key metrics — numbers must be extracted from the paper, not inferred")
        + sec("Contributions", "创新点", "contributions")
        + sec("Limitations & Open Questions", "局限与可质疑之处", "limitations")
        + sec("Highlights from Paper", "关键引文摘录", "highlights",
              "Synced from Zotero annotations — run workflow_sync_highlights to populate")
    )


# ── Zotero child note ─────────────────────────────────────────────────────────

def build_zotero_note(citekey: str, summary: str, rating: str = "⭐⭐⭐",
                      cite_in: str = "", vault_name: str = "") -> str:
    """
    Build the short Zotero child note (≤200 chars summary + Obsidian back-link).

    summary:   one-sentence summary
    rating:    star rating string
    cite_in:   section of the paper/grant where this can be cited
    vault_name: Obsidian vault name for the obsidian:// deep-link
    """
    link = ""
    if vault_name:
        link = f"\nDeep note → obsidian://open?vault={vault_name}&file={LITERATURE_FOLDER}/{citekey}"

    cite_str = f" | Cite in: {cite_in}" if cite_in else ""
    return f"{rating} {summary}{cite_str}\nStatus: pending-review{link}"


# ── Highlight formatting ──────────────────────────────────────────────────────

def format_annotations(annotations: list[dict]) -> str:
    """
    Format Zotero annotations into grouped Markdown for the
    'Highlights from Paper' section.

    Each annotation dict: {text, comment, color_label, page}
    """
    if not annotations:
        return "_No annotations found in Zotero._"

    groups: dict[str, list[dict]] = {}
    for ann in annotations:
        label = ann.get("color_label", "Note")
        groups.setdefault(label, []).append(ann)

    parts = []
    for label, items in groups.items():
        parts.append(f"### {label}\n")
        for ann in items:
            text = ann.get("text", "").strip()
            comment = ann.get("comment", "").strip()
            page = ann.get("page", "")
            page_str = f" (p. {page})" if page else ""
            if text:
                parts.append(f'> "{text}"{page_str}')
            if comment:
                parts.append(f"  💬 {comment}")
            parts.append("")
    return "\n".join(parts).strip()
