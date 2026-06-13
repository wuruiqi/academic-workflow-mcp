"""
Obsidian Local REST API client (port 27123).

Requires the "Local REST API" community plugin installed and enabled in Obsidian.
Set OBSIDIAN_API_KEY to the key shown in the plugin settings.
"""

import os
import re
from typing import Any, Optional

import httpx

OBSIDIAN_URL = os.getenv("OBSIDIAN_URL", "http://127.0.0.1:27123")
OBSIDIAN_API_KEY = os.getenv("OBSIDIAN_API_KEY", "")
LITERATURE_FOLDER = os.getenv("LITERATURE_FOLDER", "10-Literature")
VAULT_NAME = os.getenv("OBSIDIAN_VAULT_NAME", "")


def _headers(content_type: str = "text/markdown") -> dict:
    return {
        "Authorization": f"Bearer {OBSIDIAN_API_KEY}",
        "Content-Type": content_type,
    }


def _vault_url(path: str) -> str:
    return f"{OBSIDIAN_URL}/vault/{path.lstrip('/')}"


# ── read ──────────────────────────────────────────────────────────────────────

def read_note(path: str) -> Optional[str]:
    """Read a note by vault-relative path. Returns None if not found."""
    with httpx.Client(trust_env=False, timeout=10) as client:
        r = client.get(_vault_url(path), headers=_headers())
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.text


def note_exists(path: str) -> bool:
    """Check whether a note exists at the given vault-relative path."""
    return read_note(path) is not None


def search_notes(query: str, limit: int = 20) -> list[dict]:
    """
    Full-text search across the vault using Obsidian's built-in search.
    Returns a list of {filename, score, matches} dicts.
    """
    with httpx.Client(trust_env=False, timeout=15) as client:
        r = client.post(
            f"{OBSIDIAN_URL}/search/simple/",
            params={"query": query, "contextLength": 100},
            headers={"Authorization": f"Bearer {OBSIDIAN_API_KEY}"},
        )
    if r.status_code == 404:
        return []
    r.raise_for_status()
    results = r.json() if r.text else []
    return results[:limit]


# ── write ─────────────────────────────────────────────────────────────────────

def write_note(path: str, content: str) -> dict:
    """
    Create or overwrite a note at the given vault-relative path.
    Parent directories are created automatically by Obsidian.
    """
    with httpx.Client(trust_env=False, timeout=15) as client:
        r = client.put(_vault_url(path), content=content.encode("utf-8"),
                       headers=_headers())
    r.raise_for_status()
    obsidian_link = ""
    if VAULT_NAME:
        file_without_ext = path.removesuffix(".md")
        obsidian_link = f"obsidian://open?vault={VAULT_NAME}&file={file_without_ext}"
    return {"success": True, "path": path, "obsidian_link": obsidian_link}


def append_to_note(path: str, content: str) -> dict:
    """Append text to an existing note."""
    existing = read_note(path) or ""
    updated = existing.rstrip("\n") + "\n\n" + content.lstrip("\n")
    return write_note(path, updated)


def update_frontmatter_field(path: str, field: str, value: Any) -> dict:
    """
    Update a single YAML frontmatter field in an existing note.
    The note must already exist. String values are quoted automatically.
    """
    content = read_note(path)
    if content is None:
        raise FileNotFoundError(f"Note not found: {path}")

    # Check for frontmatter block
    if not content.startswith("---"):
        raise ValueError(f"Note has no YAML frontmatter: {path}")

    end = content.find("---", 3)
    if end == -1:
        raise ValueError(f"Malformed frontmatter (no closing ---): {path}")

    fm_block = content[3:end]
    body = content[end + 3:]

    # Format the new value
    if isinstance(value, str):
        formatted = f'"{value}"' if (" " in value or ":" in value) else value
    elif isinstance(value, list):
        formatted = "[" + ", ".join(str(v) for v in value) + "]"
    else:
        formatted = str(value)

    # Replace existing field or append
    pattern = re.compile(rf"^{re.escape(field)}\s*:.*$", re.MULTILINE)
    new_line = f"{field}: {formatted}"
    if pattern.search(fm_block):
        fm_block = pattern.sub(new_line, fm_block)
    else:
        fm_block = fm_block.rstrip("\n") + f"\n{new_line}\n"

    new_content = f"---{fm_block}---{body}"
    return write_note(path, new_content)


def patch_section(path: str, heading: str, content: str,
                  mode: str = "replace") -> dict:
    """
    Update the content under a specific heading in a note.

    mode:
      "replace" — replace everything between this heading and the next same/higher heading
      "append"  — append after existing content under the heading
    """
    note = read_note(path)
    if note is None:
        raise FileNotFoundError(f"Note not found: {path}")

    # Find heading level
    m = re.search(rf"^(#{1,6}) {re.escape(heading)}$", note, re.MULTILINE)
    if not m:
        raise ValueError(f"Heading '{heading}' not found in {path}")

    level = len(m.group(1))
    start = m.end()

    # Find next heading of same or higher level
    next_heading = re.search(rf"^#{{{1},{level}}} ", note[start:], re.MULTILINE)
    if next_heading:
        end = start + next_heading.start()
    else:
        end = len(note)

    section_body = note[start:end]

    if mode == "append":
        new_body = section_body.rstrip("\n") + "\n\n" + content.lstrip("\n") + "\n"
    else:
        new_body = "\n\n" + content.strip() + "\n\n"

    new_note = note[: start] + new_body + note[end:]
    return write_note(path, new_note)


def delete_note(path: str) -> dict:
    """Delete a note. No confirmation prompt (requires plugin ≥ v4)."""
    with httpx.Client(trust_env=False, timeout=10) as client:
        r = client.delete(_vault_url(path),
                          headers={"Authorization": f"Bearer {OBSIDIAN_API_KEY}"})
    if r.status_code == 404:
        return {"success": False, "reason": "not found"}
    r.raise_for_status()
    return {"success": True, "path": path}


# ── convenience ───────────────────────────────────────────────────────────────

def list_literature_notes() -> list[str]:
    """
    List all citekeys in the Literature folder.

    Returns a list of filenames without the .md extension (= citekeys).
    Returns an empty list if the folder does not exist or Obsidian is offline.
    """
    url = f"{OBSIDIAN_URL}/vault/{LITERATURE_FOLDER}/"
    try:
        with httpx.Client(trust_env=False, timeout=15) as client:
            r = client.get(url, headers={"Authorization": f"Bearer {OBSIDIAN_API_KEY}"})
        if r.status_code == 404:
            return []
        r.raise_for_status()
        data = r.json()
        files = data.get("files", [])
        return [
            f.split("/")[-1].removesuffix(".md")
            for f in files
            if f.endswith(".md")
        ]
    except Exception:
        return []


def literature_path(citekey: str) -> str:
    """Return the vault-relative path for a literature note."""
    return f"{LITERATURE_FOLDER}/{citekey}.md"


def get_note_status(citekey: str) -> Optional[str]:
    """
    Read the 'status' frontmatter field from a literature note.
    Returns None if the note doesn't exist.
    """
    content = read_note(literature_path(citekey))
    if content is None:
        return None
    m = re.search(r"^status\s*:\s*(.+)$", content, re.MULTILINE)
    return m.group(1).strip().strip('"') if m else None
