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
# 8. workflow_import_pdfs
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def workflow_import_pdfs(
    pdf_paths: list[str],
    collection: str = "",
    item_type: str = "preprint",
) -> dict:
    """
    Import PDF files into Zotero with automatic title extraction and smart deduplication.

    Improvements over zotero-mcp's zotero_add_from_file:
    1. Extracts the real title from the PDF (metadata field, then largest-font
       first-page text) instead of using the filename stem.
    2. Detects title mismatches between the filename and the PDF content — useful
       for catching mislabeled downloads (e.g. wrong paper saved under a different name).
    3. Smart deduplication:
       - If an identical file already has a PDF in Zotero → skip.
       - If a matching metadata-only entry exists (no PDF yet) → attach PDF to it
         rather than creating a duplicate parent item.
    4. Copies the PDF into <zotero_data_dir>/storage/<attachment_key>/ so Zotero
       can open it immediately without any manual "Locate File" step.

    Args:
        pdf_paths:  List of absolute file paths to PDFs.
        collection: Zotero collection name (exact, case-sensitive). Leave empty
                    for library root.
        item_type:  Zotero item type for new parent items. Default "preprint".
                    Other values: "journalArticle", "conferencePaper".

    Returns:
        {
            "imported":  [ {item_key, attachment_key, title, title_source,
                            filename_stem, title_mismatch, attached_to_existing,
                            storage_copied, path} ],
            "skipped":   [ {path, item_key, title, reason} ],
            "failed":    [ {path, error} ],
            "warnings":  [ {path, filename_stem, extracted_title, title_source,
                            message} ],   # title mismatches needing user review
            "count":     int,             # newly imported (excludes skipped)
        }
    """
    collection_key = ""
    if collection:
        try:
            collection_key = zotero.find_collection_key(collection)
        except ValueError as e:
            return {
                "imported": [], "skipped": [], "failed": [],
                "warnings": [], "count": 0, "error": str(e),
            }

    imported: list[dict] = []
    skipped: list[dict] = []
    failed: list[dict] = []
    warnings: list[dict] = []

    for path in pdf_paths:
        try:
            result = zotero.create_item_with_attachment(
                pdf_path=path,
                collection_key=collection_key,
                item_type=item_type,
            )
            result["path"] = path
            if result.get("skipped"):
                skipped.append({
                    "path": path,
                    "item_key": result["item_key"],
                    "title": result["title"],
                    "reason": result.get("skip_reason", ""),
                })
            else:
                imported.append(result)
                if result.get("title_mismatch"):
                    warnings.append({
                        "path": path,
                        "filename_stem": result.get("filename_stem", ""),
                        "extracted_title": result["title"],
                        "title_source": result.get("title_source", ""),
                        "message": (
                            f"TITLE MISMATCH — filename: \"{result.get('filename_stem','')[:80]}\" "
                            f"but PDF contains: \"{result['title'][:80]}\". "
                            "The item was imported using the PDF's actual title. "
                            "This PDF may be the wrong paper."
                        ),
                    })
        except Exception as exc:
            failed.append({"path": path, "error": str(exc)})

    tip = ""
    if imported:
        tip = (
            "Next: for each item_key, search Semantic Scholar by title, then call "
            "zotero_update_item(item_key=..., creators=[...], date='YYYY', "
            "publication_title='...', item_type='journalArticle') to fill in metadata."
        )
    if warnings:
        tip = (
            "⚠ TITLE MISMATCHES DETECTED — check 'warnings' list. "
            "Some PDFs may be wrong papers saved under incorrect filenames. "
        ) + tip

    return {
        "imported": imported,
        "skipped": skipped,
        "failed": failed,
        "warnings": warnings,
        "count": len(imported),
        "tip": tip,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 9. workflow_find_duplicates
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def workflow_find_duplicates(
    collections: list[str] = [],
    title_threshold: float = 0.85,
) -> dict:
    """
    Scan Zotero for duplicate items grouped by identical DOI or highly similar title.

    Run this before starting a reading session or after a batch import to catch
    entries that were added twice, preventing duplicate annotation work.

    Args:
        collections: Collection names to scan (e.g. ["1_SLAM与退化导航", "2_3DGS与三维重建"]).
                     Leave empty to scan the entire library.
        title_threshold: Word-overlap ratio for title similarity (default 0.85).
                         0.85 catches near-identical titles; lower values cast a wider net.

    Returns:
        {
            "duplicate_groups": [
                {
                    "reason": "Same DOI" | "Similar title",
                    "doi": str,
                    "suggested_keep": str,     # item key recommended to keep
                    "items": [
                        {key, title, year, authors, journal, doi, zotero_link}, ...
                    ],
                }
            ],
            "total_duplicates": int,   # total number of items that are duplicates
            "group_count": int,
            "tip": str,
        }
    """
    # Resolve collection names → keys
    col_keys: list[str] = []
    if collections:
        try:
            all_cols = {
                c.get("data", {}).get("name", ""): c["key"]
                for c in zotero._local("/api/users/0/collections")
            }
        except Exception:
            all_cols = {}
        not_found = []
        for name in collections:
            if name in all_cols:
                col_keys.append(all_cols[name])
            else:
                not_found.append(name)
        if not_found:
            return {"error": f"Collections not found: {not_found}. "
                             f"Available: {list(all_cols.keys())}"}

    groups = zotero.find_duplicates(
        collection_keys=col_keys or None,
        title_threshold=title_threshold,
    )

    total_dups = sum(len(g["items"]) for g in groups)

    tip = ""
    if groups:
        tip = (
            "To remove a duplicate: open Zotero, select the item to delete, "
            "right-click → Move to Trash. Then run workflow_sync_check to clean "
            "any corresponding Obsidian notes."
        )
    else:
        tip = "No duplicates found."

    return {
        "duplicate_groups": groups,
        "group_count": len(groups),
        "total_duplicates": total_dups,
        "tip": tip,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 10. workflow_sync_check
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def workflow_sync_check(
    direction: str = "both",
    auto_apply: bool = False,
) -> dict:
    """
    Bidirectional sync check between Zotero and Obsidian.

    Three checks are performed depending on ``direction``:

    1. **"trash_to_obs"** — Zotero items in trash → find orphaned Obsidian notes.
       When auto_apply=True, deletes those Obsidian notes.

    2. **"obs_to_zotero"** — Obsidian literature notes → find those whose Zotero
       item is gone (was deleted). When auto_apply=True, deletes orphan notes from
       Obsidian.  Also finds Zotero items that had Obsidian notes created via
       workflow_attach_zotero_note but the note has since been deleted; when
       auto_apply=True, moves those Zotero items to trash.

    3. **"both"** — runs both directions above.

    Default is dry_run mode (auto_apply=False) — reports findings without making
    any changes. Review the output before setting auto_apply=True.

    Args:
        direction:   "trash_to_obs" | "obs_to_zotero" | "both"
        auto_apply:  False (default) = report only. True = actually delete/trash.

    Returns:
        {
            "trash_to_obs":  {
                "zotero_trash_items": [...],
                "orphan_notes_found": [...],   # notes to delete
                "deleted_notes": [...],         # notes actually deleted (auto_apply=True)
            },
            "obs_to_zotero": {
                "obsidian_notes_total": int,
                "orphan_notes": [...],          # notes with no Zotero item → delete note
                "deleted_orphan_notes": [...],
                "items_note_deleted": [...],    # Zotero items whose notes were removed
                "trashed_items": [...],         # items actually trashed (auto_apply=True)
            },
            "auto_apply": bool,
            "summary": str,
        }
    """
    import re as _re

    # Parse zotero://select/library/items/XXXXXXXX from note frontmatter
    _ZKEY_RE = _re.compile(
        r"zotero://(?:select|open)/library/items/([A-Z0-9]{8})", _re.IGNORECASE
    )

    def _note_zotero_key(content: str) -> str:
        m = _ZKEY_RE.search(content)
        return m.group(1).upper() if m else ""

    result_trash: dict = {}
    result_obs: dict = {}

    # ── Pre-scan: build obs note map {zotero_item_key → note info} ────────────
    # Read all Obsidian notes once; used by both directions.
    obs_citekeys: list[str] = []
    obs_key_map: dict[str, dict] = {}   # zotero_item_key → {citekey, note_path}
    if direction in ("trash_to_obs", "obs_to_zotero", "both"):
        obs_citekeys = obsidian.list_literature_notes()
        for ck in obs_citekeys:
            note_path = obsidian.literature_path(ck)
            content = obsidian.read_note(note_path) or ""
            zk = _note_zotero_key(content)
            if zk:
                obs_key_map[zk] = {"citekey": ck, "note_path": note_path}

    # ── Direction 1: Zotero trash → Obsidian ──────────────────────────────────
    if direction in ("trash_to_obs", "both"):
        trash_items = zotero.get_trash_items()
        orphan_notes: list[dict] = []
        deleted_notes: list[str] = []

        for item in trash_items:
            item_key = item.get("key", "")
            note_info = obs_key_map.get(item_key)
            if note_info:
                orphan_notes.append({
                    "item_key": item_key,
                    "citekey": note_info["citekey"],
                    "title": item.get("title", ""),
                    "note_path": note_info["note_path"],
                })
                if auto_apply:
                    obsidian.delete_note(note_info["note_path"])
                    deleted_notes.append(note_info["note_path"])

        result_trash = {
            "zotero_trash_items": len(trash_items),
            "orphan_notes_found": orphan_notes,
            "deleted_notes": deleted_notes,
        }

    # ── Direction 2: Obsidian → Zotero ────────────────────────────────────────
    if direction in ("obs_to_zotero", "both"):
        orphan_obs_notes: list[dict] = []
        deleted_orphan_notes: list[str] = []
        items_note_deleted: list[dict] = []
        trashed_items: list[str] = []

        # 2a. For each Obsidian note, verify its linked Zotero item still exists
        for ck in obs_citekeys:
            note_path = obsidian.literature_path(ck)
            content = obsidian.read_note(note_path) or ""
            zk = _note_zotero_key(content)
            if not zk:
                continue  # no zotero link — not a workflow-managed note
            found = zotero.search_items(zk, limit=1)
            if not (found and found[0].get("key") == zk):
                orphan_obs_notes.append({
                    "citekey": ck,
                    "zotero_key": zk,
                    "note_path": note_path,
                    "message": f"Zotero item {zk} not found — may have been deleted",
                })
                if auto_apply:
                    obsidian.delete_note(note_path)
                    deleted_orphan_notes.append(note_path)

        # 2b. Zotero items whose obsidian:// child note no longer exists in Obsidian
        all_obs_zkeys = set(obs_key_map.keys())
        raw_items = zotero._local("/api/users/0/items",
                                  itemType="-attachment || -note", limit=500)
        for raw in raw_items:
            item_key = raw.get("key", "")
            if item_key in all_obs_zkeys:
                continue  # note still exists
            child_notes = zotero.get_item_child_notes(item_key)
            if any("obsidian://" in n for n in child_notes):
                d = raw.get("data", {})
                items_note_deleted.append({
                    "item_key": item_key,
                    "title": d.get("title", ""),
                    "message": "Obsidian note deleted (item has obsidian:// child note but note is missing)",
                })
                if auto_apply:
                    zotero.move_to_trash(item_key)
                    trashed_items.append(item_key)

        result_obs = {
            "obsidian_notes_total": len(obs_citekeys),
            "notes_with_zotero_link": len(obs_key_map),
            "orphan_notes": orphan_obs_notes,
            "deleted_orphan_notes": deleted_orphan_notes,
            "items_note_deleted": items_note_deleted,
            "trashed_items": trashed_items,
        }

    # ── Summary ───────────────────────────────────────────────────────────────
    parts = []
    if result_trash:
        n_orphan = len(result_trash.get("orphan_notes_found", []))
        n_del = len(result_trash.get("deleted_notes", []))
        parts.append(
            f"Zotero→Obsidian: {result_trash['zotero_trash_items']} trash items checked, "
            f"{n_orphan} orphan notes found"
            + (f", {n_del} deleted" if auto_apply else " (dry run)")
        )
    if result_obs:
        n_orphan2 = len(result_obs.get("orphan_notes", []))
        n_ghost = len(result_obs.get("items_note_deleted", []))
        parts.append(
            f"Obsidian→Zotero: {result_obs['obsidian_notes_total']} notes checked, "
            f"{n_orphan2} orphan notes, {n_ghost} items with deleted notes"
            + (" (applied)" if auto_apply else " (dry run)")
        )

    return {
        "trash_to_obs": result_trash,
        "obs_to_zotero": result_obs,
        "auto_apply": auto_apply,
        "summary": " | ".join(parts) if parts else "No checks performed.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    """Console entry point installed by pip."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
