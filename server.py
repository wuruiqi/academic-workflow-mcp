"""
academic-workflow-mcp — server entry point

An MCP server that bridges Zotero and Obsidian for academic literature workflows.
Compatible with any MCP client: Claude Code, Codex, OpenClaw, Cursor, etc.

Start with:
  python server.py
Or after pip install:
  academic-workflow-mcp
"""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv(Path(__file__).parent / ".env")

from workflow import zotero, obsidian, templates

mcp = FastMCP("academic-workflow")

VAULT_NAME = os.getenv("OBSIDIAN_VAULT_NAME", "")
LITERATURE_FOLDER = os.getenv("LITERATURE_FOLDER", "10-Literature")


# ─────────────────────────────────────────────────────────────────────────────
# 1. workflow_get_paper
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def workflow_get_paper(identifier: str) -> dict:
    """
    Retrieve everything needed to analyze a paper: metadata, full text, and
    PDF annotations from Zotero — all in one call.

    Use this as the first step before generating a literature note. The returned
    data gives the LLM sufficient context to fill every section of the note template.

    Args:
        identifier: Zotero item key (e.g. "7BDH2DPA"), Better BibTeX citekey
                    (e.g. "wang2024deep"), DOI, or title keywords.

    Returns:
        {
          "found": bool,
          "item": {key, citekey, title, authors, year, journal, doi,
                   abstract, tags, zotero_link},
          "fulltext": str,          # indexed PDF text (may be empty)
          "annotations": [          # PDF highlights & notes
            {type, text, comment, color_label, page}, ...
          ],
          "has_fulltext": bool,
          "has_annotations": bool,
          "note_path": str,         # expected Obsidian path for the note
          "note_exists": bool,      # whether a note already exists
        }
    """
    # 1. Locate the item in Zotero
    item: Optional[dict] = None

    # Try citekey / keyword search
    results = zotero.search_items(identifier, limit=5)
    if results:
        # Prefer exact citekey match
        exact = next((r for r in results if r.get("citekey") == identifier), None)
        item = exact or results[0]
    else:
        return {"found": False, "identifier": identifier,
                "message": "No matching item found in Zotero."}

    item_key = item["key"]
    citekey = item.get("citekey") or item_key

    # 2. Full text
    fulltext = zotero.get_fulltext(item_key)

    # 3. Annotations
    annotations = zotero.get_annotations(item_key)

    # 4. Check Obsidian
    note_path = obsidian.literature_path(citekey)
    exists = obsidian.note_exists(note_path)

    return {
        "found": True,
        "item": item,
        "fulltext": fulltext,
        "annotations": annotations,
        "has_fulltext": bool(fulltext),
        "has_annotations": bool(annotations),
        "note_path": note_path,
        "note_exists": exists,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. workflow_write_note
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def workflow_write_note(
    citekey: str,
    metadata: dict,
    sections: dict,
    overwrite: bool = False,
) -> dict:
    """
    Write a structured literature note directly to the Obsidian vault at
    10-Literature/<citekey>.md with proper YAML frontmatter and section headings.

    The note is created with status "pending-review". Call workflow_confirm_review
    after the human has checked the note.

    Args:
        citekey:  Better BibTeX citation key (used as filename, e.g. "wang2024deep").
        metadata: Dict with keys — title, authors (list[str]), year, journal,
                  doi, zotero_link. Use the 'item' dict from workflow_get_paper.
        sections: Dict mapping section keys to content strings. Recognized keys:
                    one_line_summary, research_question, methods, results,
                    contributions, limitations, relevance, highlights, further_reading
                  Any key may be omitted; the heading is still written with a placeholder.
        overwrite: If False (default) and a note already exists, returns an error
                   so you do not silently clobber a reviewed note.

    Returns:
        {"success": bool, "path": str, "obsidian_link": str, "message": str}
    """
    path = obsidian.literature_path(citekey)

    if not overwrite and obsidian.note_exists(path):
        return {
            "success": False,
            "path": path,
            "message": (
                f"Note already exists at {path}. "
                "Pass overwrite=True to replace it, or call workflow_get_note to read it first."
            ),
        }

    content = templates.build_note_skeleton(
        citekey=citekey,
        meta=metadata,
        sections=sections,
    )
    result = obsidian.write_note(path, content)
    result["message"] = (
        f"Note written to {path} with status 'pending-review'. "
        "Ask the user to review it, then call workflow_confirm_review."
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 3. workflow_attach_zotero_note
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def workflow_attach_zotero_note(
    item_key: str,
    citekey: str,
    summary: str,
    rating: str = "⭐⭐⭐",
    cite_in: str = "",
) -> dict:
    """
    Create a short child note (≤200 chars) under the Zotero item that links
    back to the Obsidian deep note.

    Requires ZOTERO_API_KEY and ZOTERO_LIBRARY_ID to be set.

    Args:
        item_key: Zotero internal item key (8-char, e.g. "7BDH2DPA").
        citekey:  Better BibTeX citekey (used to build the obsidian:// link).
        summary:  One-sentence summary of the paper (≤150 chars recommended).
        rating:   Star rating, default "⭐⭐⭐".
        cite_in:  Grant/paper section where this can be cited (e.g. "Methods 2.1").

    Returns:
        {"success": bool, "key": str, "message": str}
    """
    note_content = templates.build_zotero_note(
        citekey=citekey,
        summary=summary,
        rating=rating,
        cite_in=cite_in,
        vault_name=VAULT_NAME,
    )
    result = zotero.create_child_note(item_key, note_content)
    if result.get("success"):
        result["message"] = f"Child note created under Zotero item {item_key}."
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 4. workflow_sync_highlights
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def workflow_sync_highlights(citekey: str, item_key: str) -> dict:
    """
    Pull PDF annotations from Zotero and update the 'Highlights from Paper'
    section of the corresponding Obsidian literature note.

    Run this any time after you have highlighted the PDF in Zotero.
    Existing highlight content is replaced; metadata sections are untouched.

    Args:
        citekey:  Better BibTeX citekey (used to locate the Obsidian note).
        item_key: Zotero internal item key (needed to fetch annotations).

    Returns:
        {"success": bool, "count": int, "message": str}
    """
    annotations = zotero.get_annotations(item_key)
    if not annotations:
        return {"success": True, "count": 0,
                "message": "No annotations found in Zotero for this item."}

    formatted = templates.format_annotations(annotations)
    path = obsidian.literature_path(citekey)

    if not obsidian.note_exists(path):
        return {"success": False,
                "message": f"Note {path} does not exist. Run workflow_write_note first."}

    obsidian.patch_section(
        path,
        heading="Highlights from Paper",
        content=formatted,
        mode="replace",
    )
    return {
        "success": True,
        "count": len(annotations),
        "message": f"Synced {len(annotations)} annotations to {path}.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. workflow_confirm_review
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def workflow_confirm_review(
    citekey: str,
    item_key: str,
    tag_remove: str = "在读",
    tag_add: str = "已精读",
) -> dict:
    """
    Mark a literature note as reviewed: update the Obsidian frontmatter status
    to 'reviewed' and update the Zotero item tags.

    Call this only after the human has reviewed and approved the note.

    Args:
        citekey:    Better BibTeX citekey.
        item_key:   Zotero internal item key.
        tag_remove: Zotero tag to remove (default "在读" / "reading").
        tag_add:    Zotero tag to add (default "已精读" / "reviewed").

    Returns:
        {"success": bool, "obsidian": {...}, "zotero": {...}}
    """
    path = obsidian.literature_path(citekey)

    # Update Obsidian frontmatter
    obs_result = {"skipped": True, "reason": "Note not found"}
    if obsidian.note_exists(path):
        obs_result = obsidian.update_frontmatter_field(path, "status", "reviewed")
        obs_result = {"updated": True, "field": "status", "value": "reviewed"}

    # Update Zotero tags
    zot_result = {"skipped": True}
    if item_key:
        try:
            zot_result = zotero.update_tags(
                item_key,
                add=[tag_add],
                remove=[tag_remove],
            )
        except Exception as e:
            zot_result = {"skipped": True, "reason": str(e)}

    return {
        "success": True,
        "obsidian": obs_result,
        "zotero": zot_result,
        "message": (
            f"Note {citekey} marked as reviewed. "
            f"Obsidian: status=reviewed. Zotero: +{tag_add} -{tag_remove}."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. workflow_list_papers
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def workflow_list_papers(
    tag: str = "",
    collection: str = "",
    limit: int = 30,
    check_notes: bool = False,
) -> dict:
    """
    List papers from Zotero filtered by tag or collection, with optional
    cross-check against the Obsidian vault to see which already have notes.

    Use this to build a reading queue or to identify papers that still need
    to be processed.

    Args:
        tag:         Zotero tag to filter by (e.g. "待读" or "#待读").
                     If empty, returns all items (up to limit).
        collection:  Zotero collection name. Takes precedence over tag if both given.
        limit:       Maximum number of items to return (default 30).
        check_notes: If True, adds "note_status" to each item showing the
                     Obsidian note status (None = no note, "pending-review",
                     "reviewed", etc.). Slower when True.

    Returns:
        {"count": int, "items": [{citekey, title, authors, year, tags,
                                   date_added, note_status?}, ...]}
    """
    items = zotero.list_items(tag=tag, collection=collection, limit=limit)

    if check_notes:
        for item in items:
            ck = item.get("citekey") or item.get("key", "")
            item["note_status"] = obsidian.get_note_status(ck) if ck else None

    return {
        "count": len(items),
        "items": items,
        "tip": (
            "Pass citekey or key to workflow_get_paper to start processing a paper."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7. workflow_get_note
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def workflow_get_note(citekey: str) -> dict:
    """
    Read the current content of a literature note from the Obsidian vault.

    Useful for reviewing what has already been written, checking the status,
    or deciding whether to overwrite vs. patch a note.

    Args:
        citekey: Better BibTeX citekey (= filename without .md).

    Returns:
        {"exists": bool, "path": str, "content": str, "status": str | None}
    """
    path = obsidian.literature_path(citekey)
    content = obsidian.read_note(path)
    return {
        "exists": content is not None,
        "path": path,
        "content": content or "",
        "status": obsidian.get_note_status(citekey) if content else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    """Console entry point installed by pip."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
