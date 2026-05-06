"""Tests for ``validate_problem_olx``."""
from __future__ import annotations

import pytest

from rg_olx_export_teak._validate import validate_problem_olx


def test_valid_multiplechoice() -> None:
    assert validate_problem_olx(
        '<problem display_name="Q1">'
        '<multiplechoiceresponse>'
        '<choicegroup type="MultipleChoice">'
        '<choice correct="true">A</choice>'
        '</choicegroup></multiplechoiceresponse>'
        '</problem>'
    ) is None


def test_valid_stringresponse() -> None:
    assert validate_problem_olx(
        '<problem><stringresponse answer="42"/></problem>'
    ) is None


def test_valid_numericalresponse() -> None:
    assert validate_problem_olx(
        '<problem><numericalresponse answer="3.14"/></problem>'
    ) is None


def test_valid_choiceresponse() -> None:
    assert validate_problem_olx(
        '<problem><choiceresponse><checkboxgroup/></choiceresponse></problem>'
    ) is None


def test_valid_with_meta_first() -> None:
    # <meta> comes first, response second — still valid.
    assert validate_problem_olx(
        '<problem>'
        '<meta><tag taxonomy="d">v</tag></meta>'
        '<multiplechoiceresponse/>'
        '</problem>'
    ) is None


def test_empty_problem_rejected() -> None:
    reason = validate_problem_olx('<problem></problem>')
    assert reason is not None
    assert "response" in reason


def test_problem_with_only_text_rejected() -> None:
    reason = validate_problem_olx(
        '<problem><text>Just narration, no response.</text></problem>'
    )
    assert reason is not None
    assert "response" in reason


def test_problem_with_only_meta_rejected() -> None:
    reason = validate_problem_olx(
        '<problem><meta><tag taxonomy="d">v</tag></meta></problem>'
    )
    assert reason is not None
    assert "response" in reason


def test_problem_with_response_only_in_descendant_rejected() -> None:
    # A <multiplechoiceresponse> nested inside a <text> is NOT a direct
    # child of <problem>. The renderer dispatches on the direct child,
    # so this must be rejected.
    reason = validate_problem_olx(
        '<problem><text><multiplechoiceresponse/></text></problem>'
    )
    assert reason is not None
    assert "response" in reason


def test_invalid_xml_returns_reason() -> None:
    reason = validate_problem_olx('<problem><unclosed>')
    assert reason is not None
    assert "invalid XML" in reason


def test_non_problem_block_passes_through() -> None:
    # html, video, etc. — not our concern here; the exporter only calls
    # this for blocks whose component_type.name == "problem", but the
    # function is defensive about the root tag.
    assert validate_problem_olx('<html>Hello</html>') is None
    assert validate_problem_olx('<video display_name="x"/>') is None


def test_bytes_input_accepted() -> None:
    assert validate_problem_olx(
        b'<problem><multiplechoiceresponse/></problem>'
    ) is None


@pytest.mark.parametrize("response_tag", [
    "multiplechoiceresponse",
    "stringresponse",
    "numericalresponse",
    "choiceresponse",
    "optionresponse",
    "customresponse",
    "imageresponse",
    "formularesponse",
])
def test_known_response_types_accepted(response_tag: str) -> None:
    assert validate_problem_olx(
        f'<problem><{response_tag}/></problem>'
    ) is None


def test_namespaced_response_tag_accepted() -> None:
    # Defensive: even with an explicit namespace, suffix-match works.
    assert validate_problem_olx(
        '<problem xmlns:x="urn:test"><x:multiplechoiceresponse/></problem>'
    ) is None
