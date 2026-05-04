"""Tests for the filename allocator."""
from __future__ import annotations

import django
from django.conf import settings


# Slugify reads INSTALLED_APPS — minimal Django setup so the tests run
# without a project-level settings module.
if not settings.configured:
    settings.configure(
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
        INSTALLED_APPS=[],
        USE_TZ=True,
    )
    django.setup()


from rg_olx_export_teak._filename import FilenameAllocator  # noqa: E402


def test_unique_keys_get_plain_slugs() -> None:
    a = FilenameAllocator()
    assert a.allocate("Section 1") == "section-1"
    assert a.allocate("Section 2") == "section-2"


def test_collision_appends_hash() -> None:
    a = FilenameAllocator()
    first = a.allocate("Section 1")
    # Different key but slugifies to the same string.
    second = a.allocate("section 1")
    assert first == "section-1"
    assert second != first
    assert second.startswith("section-1-")
    # Hash suffix is 6 hex chars per project convention.
    suffix = second.removeprefix("section-1-")
    assert len(suffix) == 6
    assert all(c in "0123456789abcdef" for c in suffix)


def test_unicode_keys_preserved() -> None:
    a = FilenameAllocator()
    out = a.allocate("Перший розділ")
    assert "перший-розділ" == out


def test_repeated_collision_continues_to_disambiguate() -> None:
    a = FilenameAllocator()
    keys = ["Section 1", "section 1", "SECTION 1"]
    out = [a.allocate(k) for k in keys]
    # All three are distinct.
    assert len(set(out)) == 3
    # First is plain; the others have hash suffixes.
    assert out[0] == "section-1"
    for o in out[1:]:
        assert o.startswith("section-1-")


def test_xblock_problem_keys_match_uuid_pattern() -> None:
    # In our 0.26 LPs, local_keys are often UUIDs — they slugify to
    # themselves (lowercase + dashes already match the slug pattern).
    a = FilenameAllocator()
    uuid_str = "256739e8-c2df-4ced-bd10-8156f6cfa90b"
    assert a.allocate(uuid_str) == uuid_str
