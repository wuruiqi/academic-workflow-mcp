"""
Integration tests — require Zotero and Obsidian to be running.

Run with: pytest tests/test_connection.py -m integration -v
"""

import pytest
from workflow import zotero, obsidian


@pytest.mark.integration
def test_zotero_local_reachable():
    """Zotero local API responds on port 23119."""
    import httpx
    r = httpx.get("http://127.0.0.1:23119/connector/ping", timeout=3)
    assert r.status_code == 200


@pytest.mark.integration
def test_zotero_list_items():
    items = zotero.list_items(limit=3)
    assert isinstance(items, list)
    if items:
        assert "key" in items[0]
        assert "title" in items[0]


@pytest.mark.integration
def test_obsidian_local_reachable():
    """Obsidian REST API responds on port 27123."""
    import httpx, os
    key = os.getenv("OBSIDIAN_API_KEY", "")
    if not key:
        pytest.skip("OBSIDIAN_API_KEY not set")
    r = httpx.get(
        "http://127.0.0.1:27123/vault/",
        headers={"Authorization": f"Bearer {key}"},
        timeout=3,
    )
    assert r.status_code in (200, 404)


@pytest.mark.integration
def test_obsidian_read_write_roundtrip(tmp_path):
    """Write a test note and read it back."""
    import os
    if not os.getenv("OBSIDIAN_API_KEY"):
        pytest.skip("OBSIDIAN_API_KEY not set")

    test_path = "99-Attachments/_mcp_test.md"
    content = "# MCP Test\n\nThis file was written by academic-workflow-mcp tests.\n"

    result = obsidian.write_note(test_path, content)
    assert result["success"]

    read_back = obsidian.read_note(test_path)
    assert read_back is not None
    assert "MCP Test" in read_back

    obsidian.delete_note(test_path)
