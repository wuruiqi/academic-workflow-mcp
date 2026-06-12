"""
Zotero local API client (port 23119).

Reads from the local Zotero connector API without requiring an API key.
Write operations (tags, notes) use the Zotero Web API when credentials are supplied.
"""

import os
from typing import Any, Optional

import httpx

ZOTERO_LOCAL = os.getenv("ZOTERO_LOCAL_URL", "http://127.0.0.1:23119")
ZOTERO_API_KEY = os.getenv("ZOTERO_API_KEY", "")
ZOTERO_LIBRARY_ID = os.getenv("ZOTERO_LIBRARY_ID", "")
ZOTERO_LIBRARY_TYPE = os.getenv("ZOTERO_LIBRARY_TYPE", "user")

# Color → semantic label mapping (Zotero defaults)
ANNOTATION_COLORS: dict[str, str] = {
    "#ffd400": "Key Point",
    "#ff6666": "Critical / Question",
    "#5fb236": "Method / Technique",
    "#2ea8e5": "Data / Result",
    "#a28ae5": "Background",
    "#e56eee": "Definition",
    "#f19837": "Important",
    "#aaaaaa": "Note",
}


# ── helpers ──────────────────────────────────────────────────────────────────

def _local(path: str, **params) -> Any:
    """GET from Zotero local API. Returns parsed JSON or raises."""
    url = f"{ZOTERO_LOCAL}{path}"
    with httpx.Client(trust_env=False, timeout=10) as client:
        r = client.get(url, params=params)
    if r.status_code == 400:
        raise RuntimeError(f"Zotero local API 400: {r.text[:200]}")
    r.raise_for_status()
    return r.json()


def _web_post(path: str, payload: Any) -> Any:
    """POST to Zotero Web API. Requires ZOTERO_API_KEY."""
    if not ZOTERO_API_KEY:
        raise RuntimeError("ZOTERO_API_KEY not set — cannot write to Zotero Web API.")
    url = f"https://api.zotero.org{path}"
    headers = {
        "Zotero-API-Key": ZOTERO_API_KEY,
        "Content-Type": "application/json",
    }
    with httpx.Client(trust_env=False, timeout=15) as client:
        r = client.post(url, json=payload, headers=headers)
    r.raise_for_status()
    return r.json()


def _web_patch(path: str, payload: Any, version: int) -> Any:
    """PATCH to Zotero Web API."""
    if not ZOTERO_API_KEY:
        raise RuntimeError("ZOTERO_API_KEY not set — cannot write to Zotero Web API.")
    url = f"https://api.zotero.org{path}"
    headers = {
        "Zotero-API-Key": ZOTERO_API_KEY,
        "Content-Type": "application/json",
        "If-Unmodified-Since-Version": str(version),
    }
    with httpx.Client(trust_env=False, timeout=15) as client:
        r = client.patch(url, json=payload, headers=headers)
    r.raise_for_status()
    return r


def _lib_path() -> str:
    """Return Web API library path, e.g. /users/12345."""
    if not ZOTERO_LIBRARY_ID:
        raise RuntimeError("ZOTERO_LIBRARY_ID not set.")
    lib_type = "users" if ZOTERO_LIBRARY_TYPE == "user" else "groups"
    return f"/{lib_type}/{ZOTERO_LIBRARY_ID}"


def _extract_citekey(extra: str) -> str:
    """Parse citekey from Zotero Extra field (Better BibTeX convention)."""
    for line in (extra or "").splitlines():
        if line.lower().startswith("citation key:"):
            return line.split(":", 1)[1].strip()
    return ""


# ── public API ───────────────────────────────────────────────────────────────

def search_items(query: str, limit: int = 10) -> list[dict]:
    """
    Search Zotero library by keyword (title, author, DOI, or citekey).
    Returns a list of item summary dicts.
    """
    data = _local("/api/users/0/items", q=query, limit=limit,
                  itemType="-attachment || -note")
    return [_summarize(it) for it in data]


def search_by_tag(tag: str, limit: int = 50) -> list[dict]:
    """List items with a specific Zotero tag."""
    tag_q = tag if tag.startswith("#") else f"#{tag}"
    data = _local("/api/users/0/items", tag=tag_q, limit=limit,
                  itemType="-attachment || -note")
    return [_summarize(it) for it in data]


def get_item(item_key: str) -> dict:
    """Fetch full metadata for a single Zotero item."""
    data = _local(f"/api/users/0/items/{item_key}")
    return _summarize(data)


def get_fulltext(item_key: str) -> str:
    """
    Retrieve indexed full text for a Zotero item.
    Returns empty string if not available (PDF not indexed yet).
    """
    try:
        data = _local(f"/api/users/0/items/{item_key}/fulltext")
        return data.get("content", "")
    except Exception:
        return ""


def get_annotations(item_key: str) -> list[dict]:
    """
    Retrieve all PDF annotations (highlights, notes) for an item.
    Each annotation includes: type, text, comment, color_label, page.
    """
    try:
        children = _local(f"/api/users/0/items/{item_key}/children")
    except Exception:
        return []
    annotations = []
    for child in children:
        d = child.get("data", {})
        if d.get("itemType") != "annotation":
            continue
        color_hex = d.get("annotationColor", "").lower()
        annotations.append({
            "type": d.get("annotationType", "highlight"),
            "text": d.get("annotationText", ""),
            "comment": d.get("annotationComment", ""),
            "color": color_hex,
            "color_label": ANNOTATION_COLORS.get(color_hex, "Note"),
            "page": d.get("annotationPageLabel", ""),
        })
    return annotations


def list_items(tag: str = "", collection: str = "", limit: int = 30) -> list[dict]:
    """
    List items from Zotero, optionally filtered by tag or collection name.
    Returns item summaries sorted by date added (newest first).
    """
    if tag:
        return search_by_tag(tag, limit=limit)
    if collection:
        return _list_by_collection(collection, limit=limit)
    data = _local("/api/users/0/items", limit=limit,
                  itemType="-attachment || -note", sort="dateAdded", direction="desc")
    return [_summarize(it) for it in data]


def create_child_note(item_key: str, content: str) -> dict:
    """
    Create a child note under a Zotero item via Web API.
    Requires ZOTERO_API_KEY + ZOTERO_LIBRARY_ID.
    """
    lib = _lib_path()
    payload = [{
        "itemType": "note",
        "parentItem": item_key,
        "note": content,
        "tags": [],
    }]
    result = _web_post(f"{lib}/items", payload)
    successful = result.get("successful", {})
    if successful:
        key = list(successful.values())[0].get("key", "")
        return {"success": True, "key": key}
    return {"success": False, "detail": str(result.get("failed", {}))}


def update_tags(item_key: str, add: list[str], remove: list[str]) -> dict:
    """
    Add and/or remove tags on a Zotero item via Web API.
    Tags without '#' prefix have it added automatically.
    """
    # Normalize tags
    def norm(t: str) -> str:
        return t if t.startswith("#") else f"#{t}"

    # Get current item version + tags
    lib = _lib_path()
    url = f"https://api.zotero.org{lib}/items/{item_key}"
    with httpx.Client(trust_env=False, timeout=10) as client:
        r = client.get(url, headers={"Zotero-API-Key": ZOTERO_API_KEY})
    r.raise_for_status()
    item_data = r.json()
    version = item_data.get("version", 0)
    current_tags = item_data.get("data", {}).get("tags", [])

    remove_normalized = {norm(t) for t in remove}
    kept = [t for t in current_tags if t.get("tag", "") not in remove_normalized]
    for t in add:
        kept.append({"tag": norm(t)})

    _web_patch(f"{lib}/items/{item_key}", {"tags": kept}, version)
    return {"success": True, "tags": [t["tag"] for t in kept]}


# ── internal helpers ──────────────────────────────────────────────────────────

def _summarize(item: dict) -> dict:
    """Flatten a Zotero API item into a compact summary dict."""
    d = item.get("data", {})
    creators = d.get("creators", [])
    authors = []
    for c in creators[:5]:
        last = c.get("lastName", "")
        first = c.get("firstName", "")
        name = f"{last}, {first[0]}." if last and first else last or first
        if name:
            authors.append(name)

    return {
        "key": item.get("key", d.get("key", "")),
        "citekey": _extract_citekey(d.get("extra", "")),
        "title": d.get("title", ""),
        "authors": authors,
        "year": (d.get("date") or "")[:4],
        "journal": (d.get("publicationTitle")
                    or d.get("conferenceName")
                    or d.get("bookTitle")
                    or d.get("itemType", "")),
        "doi": d.get("DOI", ""),
        "abstract": d.get("abstractNote", ""),
        "tags": [t.get("tag", "") for t in d.get("tags", [])],
        "date_added": (d.get("dateAdded") or "")[:10],
        "zotero_link": f"zotero://select/library/items/{item.get('key', '')}",
    }


def _list_by_collection(name: str, limit: int) -> list[dict]:
    """Find collection by name then list its items."""
    cols = _local("/api/users/0/collections")
    target = next(
        (c for c in cols if c.get("data", {}).get("name", "") == name), None
    )
    if not target:
        available = [c.get("data", {}).get("name", "") for c in cols]
        raise ValueError(f"Collection '{name}' not found. Available: {available}")
    key = target["key"]
    data = _local(f"/api/users/0/collections/{key}/items",
                  limit=limit, itemType="-attachment || -note")
    return [_summarize(it) for it in data]
