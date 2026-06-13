"""
Zotero local API client (port 23119).

Reads from the local Zotero connector API without requiring an API key.
Write operations (tags, notes) use the Zotero Web API when credentials are supplied.
"""

import html as _html_mod
import os
import re
import shutil
from pathlib import Path
from typing import Any, Optional

import httpx

ZOTERO_LOCAL = os.getenv("ZOTERO_LOCAL_URL", "http://127.0.0.1:23119")
ZOTERO_API_KEY = os.getenv("ZOTERO_API_KEY", "")
ZOTERO_LIBRARY_ID = os.getenv("ZOTERO_LIBRARY_ID", "")
ZOTERO_LIBRARY_TYPE = os.getenv("ZOTERO_LIBRARY_TYPE", "user")
ZOTERO_DATA_DIR = os.getenv("ZOTERO_DATA_DIR", "")

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

_ITEM_KEY_RE = re.compile(r"^[A-Z0-9]{8}$")


def search_items(query: str, limit: int = 10) -> list[dict]:
    """Search Zotero library by keyword, DOI, or item key."""
    if _ITEM_KEY_RE.match(query):
        try:
            item = _local(f"/api/users/0/items/{query}")
            d = item.get("data", {})
            if d.get("itemType") not in ("attachment", "note"):
                return [_summarize(item)]
            parent_key = d.get("parentItem")
            if parent_key:
                parent = _local(f"/api/users/0/items/{parent_key}")
                if parent.get("data", {}).get("itemType") not in ("attachment", "note"):
                    return [_summarize(parent)]
        except Exception:
            pass

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
    """Retrieve indexed full text for a Zotero item."""
    try:
        data = _local(f"/api/users/0/items/{item_key}/fulltext")
        return data.get("content", "")
    except Exception:
        return ""


def get_annotations(item_key: str) -> list[dict]:
    """Retrieve all PDF annotations (highlights, notes) for an item."""
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
    """List items from Zotero, optionally filtered by tag or collection name."""
    if tag:
        return search_by_tag(tag, limit=limit)
    if collection:
        return _list_by_collection(collection, limit=limit)
    data = _local("/api/users/0/items", limit=limit,
                  itemType="-attachment || -note", sort="dateAdded", direction="desc")
    return [_summarize(it) for it in data]


def create_child_note(item_key: str, content: str) -> dict:
    """Create a child note under a Zotero item via Web API."""
    lib = _lib_path()
    payload = [{"itemType": "note", "parentItem": item_key, "note": content, "tags": []}]
    result = _web_post(f"{lib}/items", payload)
    successful = result.get("successful", {})
    if successful:
        key = list(successful.values())[0].get("key", "")
        return {"success": True, "key": key}
    return {"success": False, "detail": str(result.get("failed", {}))}


def update_tags(item_key: str, add: list[str], remove: list[str]) -> dict:
    """Add and/or remove tags on a Zotero item via Web API."""
    def norm(t: str) -> str:
        return t if t.startswith("#") else f"#{t}"

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


# ── title extraction and normalization ────────────────────────────────────────

# Common journal/section names that appear as the largest text on a first page
# and must not be mistaken for a paper title.
_NOT_TITLES: set[str] = {
    "remote sensing", "sensors", "powder technology", "insects", "applied sciences",
    "robotics", "electronics", "materials", "energies", "processes", "sustainability",
    "s", "a", "b", "c",
}


def _clean_title(title: str) -> str:
    """Normalize a raw PDF title: decode HTML entities, fix dashes, collapse whitespace."""
    title = _html_mod.unescape(title)
    # Normalize various dash-like Unicode code points to plain hyphen
    for ch in "‐‑‒–—―−":
        title = title.replace(ch, "-")
    # Backslash used as hyphen (PDF encoding artifact: screw\drive → screw-drive)
    title = re.sub(r"(?<=[A-Za-z])\s*\\\s*(?=[A-Za-z])", "-", title)
    # Unicode replacement char between letters → hyphen
    title = re.sub(r"(?<=[A-Za-z])�+(?=[A-Za-z])", "-", title)
    title = title.replace("�", "")
    # Collapse whitespace
    title = re.sub(r"\s+", " ", title).strip()
    # Title-case if ALL CAPS and >= 4 words (avoids mangling short acronym titles)
    words_list = title.split()
    if (len(words_list) >= 4
            and all(w.isupper() or not w.isalpha() for w in words_list)):
        title = title.title()
    return title


def _titles_exact(t1: str, t2: str) -> bool:
    """Case-insensitive, punctuation-stripped equality."""
    def norm(s: str) -> str:
        return re.sub(r"[^\w\s]", "", s.lower()).strip()
    return bool(t1) and bool(t2) and norm(t1) == norm(t2)


def _titles_similar(t1: str, t2: str, threshold: float = 0.65) -> bool:
    """True if t1 and t2 share >= threshold fraction of meaningful words."""
    stop = {"a", "an", "the", "of", "for", "in", "on", "with", "and", "to",
            "via", "by", "using", "based", "from"}

    def words(s: str) -> set:
        return set(re.sub(r"[^\w\s]", "", s.lower()).split()) - stop

    w1, w2 = words(t1), words(t2)
    if not w1 or not w2:
        return False
    return len(w1 & w2) / min(len(w1), len(w2)) >= threshold


def extract_title_from_pdf(pdf_path: str) -> tuple[str, str]:
    """
    Extract the academic title from a PDF file.

    Strategy:
    1. PDF /Title metadata field (most reliable when properly set).
    2. First-page largest-font text in the top 60% of the page.

    Returns (title, source) where source is "metadata", "page_text", or ""
    (empty = extraction failed; caller should fall back to filename stem).
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return "", ""

    try:
        doc = fitz.open(str(pdf_path))
    except Exception:
        return "", ""

    try:
        # ── 1. PDF metadata ───────────────────────────────────────────────────
        meta = (doc.metadata or {}).get("title", "").strip()
        if meta and 10 < len(meta) < 400:
            _bad = ("microsoft word", "untitled", ".docx", ".doc",
                    "pdflatex", "latex document", "acrobat")
            if not any(p in meta.lower() for p in _bad):
                return _clean_title(meta), "metadata"

        # ── 2. First-page font-size analysis ──────────────────────────────────
        page = doc[0]
        page_h = page.rect.height
        line_data: list[tuple[float, float, str]] = []

        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                y0 = line["bbox"][1]
                if y0 > page_h * 0.62:
                    continue
                spans = line.get("spans", [])
                sizes = [sp["size"] for sp in spans if sp.get("size", 0) > 7]
                text = " ".join(sp.get("text", "").strip() for sp in spans).strip()
                if text and sizes:
                    line_data.append((max(sizes), y0, text))

        if not line_data:
            return "", ""

        max_size = max(d[0] for d in line_data)
        big_lines = sorted(
            [(y, t) for s, y, t in line_data if s >= max_size * 0.88],
            key=lambda x: x[0],
        )

        if not big_lines:
            return "", ""

        # Collect consecutive lines; stop on a large vertical gap
        parts = [big_lines[0][1]]
        for i in range(1, len(big_lines)):
            if big_lines[i][0] - big_lines[i - 1][0] > 50:
                break
            parts.append(big_lines[i][1])

        title = _clean_title(" ".join(parts))

        # Reject obvious non-titles (journal names, single words, too short)
        if (len(title) < 12
                or title.lower().strip() in _NOT_TITLES
                or len(title.split()) < 4):
            return "", ""

        return title, "page_text"

    except Exception:
        return "", ""
    finally:
        try:
            doc.close()
        except Exception:
            pass


# ── import helpers ────────────────────────────────────────────────────────────

def _find_zotero_data_dir() -> str:
    """Locate Zotero's data directory."""
    if ZOTERO_DATA_DIR:
        return ZOTERO_DATA_DIR
    username = os.environ.get("USERNAME", os.environ.get("USER", ""))
    candidates = [
        Path("C:/Users") / username / "Zotero",
        Path("D:/qq/zotero"),
        Path("C:/Users") / username / "Documents/Zotero",
        Path.home() / "Zotero",
    ]
    for p in candidates:
        if (p / "zotero.sqlite").exists():
            return str(p)
    return ""


def find_collection_key(name: str) -> str:
    """Return the Zotero collection key for the given collection name."""
    cols = _local("/api/users/0/collections")
    for c in cols:
        if c.get("data", {}).get("name", "") == name:
            return c["key"]
    available = [c.get("data", {}).get("name", "") for c in cols]
    raise ValueError(f"Collection '{name}' not found. Available: {available}")


def _item_has_pdf(item_key: str) -> bool:
    """Return True if the Zotero item already has a PDF attachment child."""
    try:
        children = _local(f"/api/users/0/items/{item_key}/children")
        return any(
            c.get("data", {}).get("contentType") == "application/pdf"
            or c.get("data", {}).get("linkMode") in ("imported_file", "linked_file")
            for c in children
        )
    except Exception:
        return False


def check_pdf_exists(filename: str, extracted_title: str = "") -> tuple[bool, str, bool]:
    """
    Check whether a PDF is already represented in Zotero.

    Returns (found, item_key, has_attachment):
    - (False, "", False)  — not found; proceed with full import.
    - (True, key, True)   — already has a PDF; skip.
    - (True, key, False)  — metadata entry exists without PDF; attach to it.

    Within title-based matches, items WITHOUT a PDF are preferred so the PDF
    gets attached to an existing metadata-only entry rather than creating a
    duplicate parent item.
    """
    stem = Path(filename).stem

    # ── Check 1: Attachment filename match ────────────────────────────────────
    try:
        att_results = _local("/api/users/0/items", q=stem[:80],
                             itemType="attachment", limit=10)
        for item in att_results:
            d = item.get("data", {})
            if d.get("filename", "") == filename or d.get("title", "") == filename:
                parent_key = d.get("parentItem", item.get("key", ""))
                return True, parent_key, True
    except Exception:
        pass

    # ── Check 2: Title-based match ────────────────────────────────────────────
    titles_to_try: list[str] = list(dict.fromkeys(
        t for t in [extracted_title, stem] if t
    ))

    for title_q in titles_to_try:
        try:
            results = _local("/api/users/0/items", q=title_q[:80],
                             itemType="-attachment || -note", limit=15)
        except Exception:
            continue

        exact_no_pdf: Optional[str] = None
        exact_has_pdf: Optional[str] = None
        fuzzy_no_pdf: Optional[str] = None

        for item in results:
            item_title = item.get("data", {}).get("title", "")
            item_key = item.get("key", "")

            is_exact = (_titles_exact(item_title, title_q)
                        or _titles_exact(item_title, stem))
            is_fuzzy = (not is_exact
                        and (_titles_similar(item_title, title_q)
                             or _titles_similar(item_title, stem)))

            if not is_exact and not is_fuzzy:
                continue

            has_pdf = _item_has_pdf(item_key)

            if is_exact:
                if not has_pdf and exact_no_pdf is None:
                    exact_no_pdf = item_key
                elif has_pdf and exact_has_pdf is None:
                    exact_has_pdf = item_key
            elif is_fuzzy and not has_pdf and fuzzy_no_pdf is None:
                fuzzy_no_pdf = item_key

        # Priority: exact without PDF > exact with PDF > fuzzy without PDF
        if exact_no_pdf:
            return True, exact_no_pdf, False
        if exact_has_pdf:
            return True, exact_has_pdf, True
        if fuzzy_no_pdf:
            return True, fuzzy_no_pdf, False

    return False, "", False


def get_trash_items() -> list[dict]:
    """
    Return all top-level items currently in the Zotero trash.
    Uses the Zotero Web API (requires ZOTERO_API_KEY + ZOTERO_LIBRARY_ID).
    """
    lib = _lib_path()
    url = f"https://api.zotero.org{lib}/items/trash"
    with httpx.Client(trust_env=False, timeout=15) as client:
        r = client.get(url, headers={"Zotero-API-Key": ZOTERO_API_KEY})
    r.raise_for_status()
    return [
        _summarize(item) for item in r.json()
        if item.get("data", {}).get("itemType") not in ("attachment", "note")
    ]


def move_to_trash(item_key: str) -> dict:
    """
    Move a Zotero item to the trash by setting deleted=1 via Web API.
    Requires ZOTERO_API_KEY + ZOTERO_LIBRARY_ID.
    """
    lib = _lib_path()
    url = f"https://api.zotero.org{lib}/items/{item_key}"
    with httpx.Client(trust_env=False, timeout=10) as client:
        r = client.get(url, headers={"Zotero-API-Key": ZOTERO_API_KEY})
    r.raise_for_status()
    version = r.json().get("version", 0)
    _web_patch(f"{lib}/items/{item_key}", {"deleted": 1}, version)
    return {"success": True, "item_key": item_key}


def find_duplicates(
    collection_keys: list[str] = None,
    title_threshold: float = 0.85,
) -> list[dict]:
    """
    Scan Zotero items for duplicates grouped by DOI (exact) or title similarity.

    Args:
        collection_keys: List of collection keys to scan.  If None or empty,
                         scans the entire library (up to 500 items).
        title_threshold: Word-overlap threshold for title similarity (default 0.85).
                         Lower values catch more duplicates but risk false positives.

    Returns:
        A list of duplicate groups, each with:
        {
            "reason": str,          # "Same DOI" | "Similar title"
            "doi": str,             # present when reason == "Same DOI"
            "items": [              # >= 2 items in the group
                {key, title, year, authors, journal, doi, zotero_link}, ...
            ],
            "suggested_keep": str,  # key of the item with more metadata / has PDF
        }
    """
    # ── Collect items ──────────────────────────────────────────────────────────
    if collection_keys:
        raw: list[dict] = []
        seen_keys: set[str] = set()
        for ck in collection_keys:
            try:
                page = _local(f"/api/users/0/collections/{ck}/items",
                              itemType="-attachment || -note", limit=200)
                for item in page:
                    k = item.get("key", "")
                    if k and k not in seen_keys:
                        raw.append(item)
                        seen_keys.add(k)
            except Exception:
                pass
    else:
        raw = _local("/api/users/0/items",
                     itemType="-attachment || -note", limit=500)

    # Filter out attachment / note items that slipped through the API query
    items = [
        _summarize(i) for i in raw
        if i.get("data", {}).get("itemType") not in ("attachment", "note")
    ]

    # ── Group by DOI ──────────────────────────────────────────────────────────
    doi_map: dict[str, list[dict]] = {}
    for item in items:
        doi = (item.get("doi") or "").strip().lower()
        if doi:
            doi_map.setdefault(doi, []).append(item)

    groups: list[dict] = []
    doi_grouped_keys: set[str] = set()
    for doi, grp in doi_map.items():
        if len(grp) > 1:
            groups.append({
                "reason": "Same DOI",
                "doi": doi,
                "items": grp,
                "suggested_keep": _pick_best(grp),
            })
            for item in grp:
                doi_grouped_keys.add(item["key"])

    # ── Group by title similarity (among items not already in a DOI group) ────
    remaining = [i for i in items if i["key"] not in doi_grouped_keys]
    used: set[str] = set()
    for i, item1 in enumerate(remaining):
        if item1["key"] in used:
            continue
        grp = [item1]
        for item2 in remaining[i + 1:]:
            if item2["key"] in used:
                continue
            if _titles_similar(item1["title"], item2["title"], title_threshold):
                grp.append(item2)
                used.add(item2["key"])
        if len(grp) > 1:
            used.add(item1["key"])
            groups.append({
                "reason": "Similar title",
                "doi": "",
                "items": grp,
                "suggested_keep": _pick_best(grp),
            })

    return groups


def _pick_best(items: list[dict]) -> str:
    """Heuristic: prefer the item with more metadata fields populated."""
    def score(item: dict) -> int:
        return (
            bool(item.get("doi")) * 3
            + bool(item.get("authors")) * 2
            + bool(item.get("year")) * 2
            + bool(item.get("journal")) * 1
        )
    return max(items, key=score)["key"]


def get_items_with_citekeys(limit: int = 500) -> list[dict]:
    """
    Return all library items that have a Better BibTeX citekey in their Extra field.
    Used for Obsidian sync checks.
    """
    raw = _local("/api/users/0/items", itemType="-attachment || -note", limit=limit)
    return [_summarize(i) for i in raw if _extract_citekey(i.get("data", {}).get("extra", ""))]


def get_item_child_notes(item_key: str) -> list[str]:
    """Return the HTML content of all child notes for a Zotero item."""
    try:
        children = _local(f"/api/users/0/items/{item_key}/children")
        return [
            c.get("data", {}).get("note", "")
            for c in children
            if c.get("data", {}).get("itemType") == "note"
        ]
    except Exception:
        return []


def create_item_with_attachment(
    pdf_path: str,
    collection_key: str = "",
    item_type: str = "preprint",
) -> dict:
    """
    Import a single PDF into Zotero with title extraction and smart deduplication.

    Steps:
    0. Extract the real title from the PDF (PyMuPDF metadata then page-text analysis).
    1. Dedup check:
       - Already has PDF → skip.
       - Metadata entry exists without PDF → attach to it (no new parent created).
       - Not found → create new parent + attachment.
    2. Create imported_file attachment record.
    3. Copy PDF into <zotero_data_dir>/storage/<attachment_key>/.

    Returns a dict with keys:
        item_key, attachment_key, title, title_source, filename_stem,
        title_mismatch, attached_to_existing, storage_copied, storage_path,
        skipped, skip_reason
    """
    pdf = Path(pdf_path)
    if not pdf.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    filename = pdf.name

    # ── Extract real title from PDF ───────────────────────────────────────────
    extracted_title, title_source = extract_title_from_pdf(pdf_path)
    title = extracted_title if extracted_title else pdf.stem

    # Flag when PDF content title differs significantly from the filename stem.
    # Threshold 0.6 catches domain-word false-positives (e.g. "path planning"
    # appearing in two completely different papers) while still tolerating
    # minor title variations like added/dropped subtitles.
    title_mismatch = bool(
        extracted_title
        and not _titles_similar(pdf.stem, extracted_title, threshold=0.6)
    )

    # ── Deduplication ─────────────────────────────────────────────────────────
    is_dup, existing_key, existing_has_pdf = check_pdf_exists(filename, extracted_title)

    if is_dup and existing_has_pdf:
        return {
            "item_key": existing_key,
            "attachment_key": "",
            "title": title,
            "title_source": title_source or "filename",
            "filename_stem": pdf.stem,
            "title_mismatch": title_mismatch,
            "attached_to_existing": False,
            "storage_copied": False,
            "storage_path": "",
            "skipped": True,
            "skip_reason": f"Already in Zotero with PDF (item key: {existing_key})",
        }

    lib = _lib_path()
    attached_to_existing = False

    if is_dup and not existing_has_pdf:
        # Attach to existing metadata-only entry
        parent_key = existing_key
        attached_to_existing = True
    else:
        # Create new parent item with the extracted title
        parent_result = _web_post(f"{lib}/items", [{
            "itemType": item_type,
            "title": title,
            "collections": [collection_key] if collection_key else [],
            "tags": [],
        }])
        parent_ok = parent_result.get("successful", {})
        if not parent_ok:
            raise RuntimeError(
                f"Failed to create parent item: {parent_result.get('failed', {})}"
            )
        parent_key = list(parent_ok.values())[0]["key"]

    # ── Attachment record ─────────────────────────────────────────────────────
    att_result = _web_post(f"{lib}/items", [{
        "itemType": "attachment",
        "parentItem": parent_key,
        "linkMode": "imported_file",
        "title": filename,
        "filename": filename,
        "contentType": "application/pdf",
        "tags": [],
    }])
    att_ok = att_result.get("successful", {})
    if not att_ok:
        raise RuntimeError(
            f"Failed to create attachment: {att_result.get('failed', {})}"
        )
    att_key = list(att_ok.values())[0]["key"]

    # ── Copy PDF to Zotero storage ────────────────────────────────────────────
    data_dir = _find_zotero_data_dir()
    storage_path = ""
    if data_dir:
        dest_dir = Path(data_dir) / "storage" / att_key
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / filename
        shutil.copy2(pdf_path, dest)
        storage_path = str(dest)

    return {
        "item_key": parent_key,
        "attachment_key": att_key,
        "title": title,
        "title_source": title_source or "filename",
        "filename_stem": pdf.stem,
        "title_mismatch": title_mismatch,
        "attached_to_existing": attached_to_existing,
        "storage_copied": bool(data_dir),
        "storage_path": storage_path,
        "skipped": False,
        "skip_reason": "",
    }
