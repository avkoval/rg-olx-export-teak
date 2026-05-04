"""Tests for ``extract_tag_groups`` (pure helper).

The live ``tag_groups_for_entity`` is exercised in the end-to-end test
against the Tutor LMS DB; here we only test the row-grouping logic with
duck-typed mock rows.
"""
from __future__ import annotations

from dataclasses import dataclass

from rg_olx_export_teak.tag_query import extract_tag_groups


@dataclass
class _FakeTaxonomy:
    export_id: str | None


@dataclass
class _FakeObjectTag:
    taxonomy: _FakeTaxonomy
    _value: str | None


def _row(export_id: str | None, value: str | None) -> _FakeObjectTag:
    return _FakeObjectTag(_FakeTaxonomy(export_id), value)


def test_empty_input() -> None:
    assert extract_tag_groups([]) == {}


def test_single_row() -> None:
    assert extract_tag_groups([_row("discipline", "civil-law")]) == {
        "discipline": ["civil-law"],
    }


def test_multiple_taxonomies_grouped() -> None:
    rows = [
        _row("discipline", "civil-law"),
        _row("section", "property-rights"),
        _row("discipline", "criminal-law"),
    ]
    out = extract_tag_groups(rows)
    assert out == {
        "discipline": ["civil-law", "criminal-law"],
        "section": ["property-rights"],
    }


def test_dedup_within_taxonomy() -> None:
    rows = [
        _row("discipline", "civil-law"),
        _row("discipline", "civil-law"),
        _row("discipline", "criminal-law"),
    ]
    assert extract_tag_groups(rows) == {
        "discipline": ["civil-law", "criminal-law"],
    }


def test_empty_export_id_skipped() -> None:
    rows = [
        _row("", "ignored"),
        _row(None, "also-ignored"),
        _row("discipline", "kept"),
    ]
    assert extract_tag_groups(rows) == {"discipline": ["kept"]}


def test_empty_value_skipped() -> None:
    rows = [
        _row("discipline", ""),
        _row("discipline", None),
        _row("discipline", "kept"),
    ]
    assert extract_tag_groups(rows) == {"discipline": ["kept"]}


def test_first_seen_order_preserved_within_taxonomy() -> None:
    # The live queryset will pre-order; the helper's job is to dedup
    # without disturbing the input order. Verify both: input order kept,
    # duplicate after first appearance dropped.
    rows = [
        _row("discipline", "z"),
        _row("discipline", "a"),
        _row("discipline", "z"),  # dup of first
        _row("discipline", "m"),
    ]
    assert extract_tag_groups(rows) == {"discipline": ["z", "a", "m"]}
