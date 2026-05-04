"""Unit tests for ``inject_meta_block`` (pure XML transform).

Covers ADR-0006 §D1's expected emit shape:

- ``<meta>`` first child of ``<problem>``;
- one ``<tag taxonomy="X">VALUE</tag>`` per (taxonomy, value);
- taxonomies sorted alphabetically (deterministic);
- non-problem blocks pass through unchanged;
- empty input dict → no ``<meta>`` (no empty container);
- existing ``<meta>`` is replaced, not duplicated;
- special characters escaped properly.
"""
from __future__ import annotations

from lxml import etree

from rg_olx_export_teak.meta_xml import inject_meta_block


def _problem_xml() -> str:
    return (
        '<problem display_name="Q1">'
        '<multiplechoiceresponse>'
        '<choicegroup type="MultipleChoice">'
        '<choice correct="false">A</choice>'
        '<choice correct="true">B</choice>'
        '</choicegroup>'
        '</multiplechoiceresponse>'
        '</problem>'
    )


def test_no_meta_when_no_tags() -> None:
    out = inject_meta_block(_problem_xml(), {})
    assert "<meta>" not in out
    # input shape preserved
    assert "<multiplechoiceresponse" in out


def test_meta_inserted_as_first_child() -> None:
    out = inject_meta_block(_problem_xml(), {"discipline": ["civil-law"]})
    root = etree.fromstring(out.encode())
    children = list(root)
    assert children[0].tag == "meta"
    assert children[1].tag == "multiplechoiceresponse"


def test_single_taxonomy_single_value() -> None:
    out = inject_meta_block(_problem_xml(), {"discipline": ["civil-law"]})
    root = etree.fromstring(out.encode())
    tag = root.find("meta/tag")
    assert tag.get("taxonomy") == "discipline"
    assert tag.text == "civil-law"


def test_multiple_taxonomies_sorted() -> None:
    out = inject_meta_block(
        _problem_xml(),
        # Insertion order: section first, but sorted output puts discipline first.
        {"section": ["property-rights"], "discipline": ["civil-law"]},
    )
    root = etree.fromstring(out.encode())
    tags = root.findall("meta/tag")
    assert [t.get("taxonomy") for t in tags] == ["discipline", "section"]
    assert [t.text for t in tags] == ["civil-law", "property-rights"]


def test_multiple_values_within_taxonomy() -> None:
    out = inject_meta_block(
        _problem_xml(),
        {"discipline": ["civil-law", "criminal-law"]},
    )
    root = etree.fromstring(out.encode())
    tags = root.findall("meta/tag")
    assert [t.text for t in tags] == ["civil-law", "criminal-law"]
    assert all(t.get("taxonomy") == "discipline" for t in tags)


def test_duplicate_values_dropped() -> None:
    out = inject_meta_block(
        _problem_xml(),
        {"discipline": ["civil-law", "civil-law", "criminal-law"]},
    )
    root = etree.fromstring(out.encode())
    tags = root.findall("meta/tag")
    assert [t.text for t in tags] == ["civil-law", "criminal-law"]


def test_empty_taxonomy_export_id_skipped() -> None:
    out = inject_meta_block(
        _problem_xml(),
        {"": ["x"], "discipline": ["civil-law"]},
    )
    root = etree.fromstring(out.encode())
    tags = root.findall("meta/tag")
    assert [t.get("taxonomy") for t in tags] == ["discipline"]


def test_non_problem_passes_through() -> None:
    html = '<html>some content</html>'
    out = inject_meta_block(html, {"discipline": ["civil-law"]})
    assert out == html


def test_video_passes_through() -> None:
    video = '<video display_name="Demo" url_name="vid1"/>'
    out = inject_meta_block(video, {"discipline": ["civil-law"]})
    assert out == video


def test_existing_meta_replaced_not_duplicated() -> None:
    pre_existing = (
        '<problem display_name="Q1">'
        '<meta><tag taxonomy="old">stale</tag></meta>'
        '<multiplechoiceresponse/>'
        '</problem>'
    )
    out = inject_meta_block(pre_existing, {"discipline": ["civil-law"]})
    root = etree.fromstring(out.encode())
    metas = root.findall("meta")
    assert len(metas) == 1
    tags = metas[0].findall("tag")
    assert [t.get("taxonomy") for t in tags] == ["discipline"]
    assert [t.text for t in tags] == ["civil-law"]


def test_xml_special_chars_escaped_in_value() -> None:
    out = inject_meta_block(
        _problem_xml(),
        {"discipline": ['<script>alert("x") & evil</script>']},
    )
    # Raw < > & " must NOT appear unescaped in the value text.
    assert "<script>alert" not in out
    # Round-trip parse to confirm valid XML and correct decoded text.
    root = etree.fromstring(out.encode())
    tag = root.find("meta/tag")
    assert tag.text == '<script>alert("x") & evil</script>'


def test_special_chars_in_export_id_kept_in_attribute() -> None:
    # export_id is used as an attribute value; lxml escapes it on serialisation.
    out = inject_meta_block(
        _problem_xml(),
        {'tax-with-"quote"-and-&': ["v"]},
    )
    root = etree.fromstring(out.encode())
    tag = root.find("meta/tag")
    assert tag.get("taxonomy") == 'tax-with-"quote"-and-&'


def test_invalid_xml_returns_unchanged() -> None:
    bad = "<problem><unclosed>"
    out = inject_meta_block(bad, {"discipline": ["civil-law"]})
    assert out == bad


def test_bytes_input_accepted() -> None:
    out = inject_meta_block(_problem_xml().encode(), {"discipline": ["civil-law"]})
    assert "<meta>" in out
    assert isinstance(out, str)


def test_set_values_emit_deduped() -> None:
    # Sets don't preserve order; the helper still dedupes and emits both.
    # We don't assert ordering here — just that both values appear.
    out = inject_meta_block(
        _problem_xml(),
        {"discipline": {"civil-law", "criminal-law"}},
    )
    root = etree.fromstring(out.encode())
    tags = root.findall("meta/tag")
    assert {t.text for t in tags} == {"civil-law", "criminal-law"}
    assert all(t.get("taxonomy") == "discipline" for t in tags)
