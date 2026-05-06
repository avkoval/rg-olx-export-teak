"""Tests for the download-filename helper used by the admin action.

The admin action itself depends on a live Django + ``openedx-learning``
ORM and is exercised end-to-end inside a Tutor deployment, not here.
"""
from __future__ import annotations

from rg_olx_export_teak._filename import safe_zip_filename


def test_v2_library_key() -> None:
    assert safe_zip_filename("lib:KSK:test-export") == "lib_KSK_test-export.zip"


def test_no_colons() -> None:
    assert safe_zip_filename("plain-key") == "plain-key.zip"


def test_path_separators_replaced() -> None:
    assert safe_zip_filename("a/b\\c:d") == "a_b_c_d.zip"


def test_unicode_preserved() -> None:
    # Slugification is intentionally NOT applied — we want the filename
    # recognisable as derived from the LP key, not normalised.
    assert safe_zip_filename("lib:КСК:тест") == "lib_КСК_тест.zip"
