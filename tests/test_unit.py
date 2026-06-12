"""
Unit tests — no Zotero or Obsidian required.
Tests cover template generation and formatting helpers.
"""

import pytest
from workflow.templates import (
    build_frontmatter,
    build_note_skeleton,
    build_zotero_note,
    format_annotations,
)


SAMPLE_META = {
    "title": "Deep SLAM with Infrared Enhancement",
    "authors": ["Dong, J.", "Zhang, C."],
    "year": "2026",
    "journal": "Ordnance Industry Automation",
    "doi": "10.7690/bgzdh.2026.01.001",
    "zotero_link": "zotero://select/library/items/7BDH2DPA",
}


def test_build_frontmatter_contains_required_fields():
    fm = build_frontmatter("dongjinxiang2026", SAMPLE_META)
    assert 'citekey: "dongjinxiang2026"' in fm
    assert "status: pending-review" in fm
    assert "tags: [literature]" in fm
    assert "zotero://" in fm


def test_build_note_skeleton_has_all_headings():
    note = build_note_skeleton("dongjinxiang2026", SAMPLE_META)
    for heading in [
        "One-line Summary",
        "Research Question",
        "Methods",
        "Key Results",
        "Contributions",
        "Limitations",
        "Relevance to My Research",
        "Highlights from Paper",
        "Further Reading",
    ]:
        assert heading in note, f"Missing heading: {heading}"


def test_build_note_skeleton_with_sections():
    sections = {
        "one_line_summary": "A novel SLAM approach using infrared cameras.",
        "methods": "Infrared-visible fusion with Kalman filtering.",
    }
    note = build_note_skeleton("dongjinxiang2026", SAMPLE_META, sections)
    assert "A novel SLAM approach" in note
    assert "Kalman filtering" in note


def test_build_zotero_note_basic():
    note = build_zotero_note(
        citekey="dongjinxiang2026",
        summary="Solves SLAM degradation using IR enhancement.",
        rating="⭐⭐⭐⭐",
    )
    assert "⭐⭐⭐⭐" in note
    assert "Solves SLAM" in note
    assert "pending-review" in note


def test_build_zotero_note_with_vault_link():
    note = build_zotero_note(
        citekey="dongjinxiang2026",
        summary="Summary here.",
        vault_name="Research",
    )
    assert "obsidian://open?vault=Research" in note
    assert "dongjinxiang2026" in note


def test_format_annotations_empty():
    result = format_annotations([])
    assert "No annotations" in result


def test_format_annotations_groups_by_color():
    annotations = [
        {"type": "highlight", "text": "Core idea", "comment": "",
         "color_label": "Key Point", "page": "3"},
        {"type": "highlight", "text": "Algorithm detail", "comment": "interesting",
         "color_label": "Method / Technique", "page": "5"},
        {"type": "highlight", "text": "Another key point", "comment": "",
         "color_label": "Key Point", "page": "7"},
    ]
    result = format_annotations(annotations)
    assert "### Key Point" in result
    assert "### Method / Technique" in result
    assert "Core idea" in result
    assert "(p. 3)" in result
    assert "interesting" in result
