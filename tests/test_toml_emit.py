"""Tests for the TOML emitters.

The acceptance bar is "openedx-core 0.45's ``LearningPackageUnzipper``
parses our output the same way it parses its own fixture." We don't run
the unzipper here (that's the integration test in a later phase) — we
just round-trip-parse with ``tomlkit`` and assert structural shape.

The reference fixture used as a sanity benchmark:
``tests/openedx_content/applets/backup_restore/fixtures/library_backup/``
in the openedx-core repo.
"""
from __future__ import annotations

from datetime import datetime, timezone

import tomlkit

from rg_olx_export_teak.records import (
    CollectionRecord,
    EntityRecord,
    EntityVersionRecord,
    ExportContext,
    LearningPackageRecord,
)
from rg_olx_export_teak.toml_emit import (
    emit_collection_toml,
    emit_entity_toml,
    emit_package_toml,
)


def _ctx() -> ExportContext:
    return ExportContext(
        created_at=datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc),
        created_by="lp_user",
        created_by_email="lp_user@example.com",
        origin_server="cms.test",
    )


def _lp() -> LearningPackageRecord:
    return LearningPackageRecord(
        title="Library test",
        key="lib:WGU:LIB_C001",
        description="",
        created=datetime(2025, 8, 19, 4, 25, 10, 988166, tzinfo=timezone.utc),
        updated=datetime(2025, 8, 19, 4, 25, 10, 988166, tzinfo=timezone.utc),
    )


# --- package.toml ---------------------------------------------------------


def test_package_toml_round_trips() -> None:
    out = emit_package_toml(_lp(), _ctx())
    parsed = tomlkit.parse(out)
    assert parsed["meta"]["format_version"] == 1
    assert parsed["meta"]["created_by"] == "lp_user"
    assert parsed["meta"]["created_by_email"] == "lp_user@example.com"
    assert parsed["meta"]["origin_server"] == "cms.test"
    assert parsed["learning_package"]["title"] == "Library test"
    assert parsed["learning_package"]["key"] == "lib:WGU:LIB_C001"
    assert parsed["learning_package"]["description"] == ""


def test_package_toml_omits_optional_meta_fields() -> None:
    ctx = ExportContext(
        created_at=datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc),
    )
    out = emit_package_toml(_lp(), ctx)
    parsed = tomlkit.parse(out)
    # Only format_version + created_at — no created_by / email / origin_server keys.
    assert "created_by" not in parsed["meta"]
    assert "created_by_email" not in parsed["meta"]
    assert "origin_server" not in parsed["meta"]
    assert parsed["meta"]["format_version"] == 1


def test_package_toml_meta_block_first_in_document() -> None:
    # The reference fixture has [meta] before [learning_package]. Order matters
    # for human-readable diffs even though TOML parsers don't require it.
    out = emit_package_toml(_lp(), _ctx())
    meta_pos = out.index("[meta]")
    lp_pos = out.index("[learning_package]")
    assert meta_pos < lp_pos


# --- entity TOML — components ---------------------------------------------


def test_entity_toml_with_published_version() -> None:
    e = EntityRecord(
        can_stand_alone=True,
        key="xblock.v1:problem:abc-123",
        created=datetime(2025, 9, 4, 22, 37, 24, tzinfo=timezone.utc),
        versions=[EntityVersionRecord(title="Q1", version_num=2)],
        draft_version_num=2,
        published_version_num=2,
    )
    out = emit_entity_toml(e)
    parsed = tomlkit.parse(out)
    assert parsed["entity"]["can_stand_alone"] is True
    assert parsed["entity"]["key"] == "xblock.v1:problem:abc-123"
    assert parsed["entity"]["draft"]["version_num"] == 2
    assert parsed["entity"]["published"]["version_num"] == 2
    assert "container" not in parsed["entity"]
    versions = parsed["version"]
    assert len(versions) == 1
    assert versions[0]["title"] == "Q1"
    assert versions[0]["version_num"] == 2


def test_entity_toml_no_published_emits_comment() -> None:
    e = EntityRecord(
        can_stand_alone=True,
        key="xblock.v1:problem:never-published",
        created=datetime(2025, 9, 4, 22, 37, 24, tzinfo=timezone.utc),
        versions=[EntityVersionRecord(title="Draft only", version_num=1)],
        draft_version_num=1,
        published_version_num=None,
    )
    out = emit_entity_toml(e)
    # tomlkit preserves the comment in the table; round-trip parse still yields
    # an empty published table — the importer reads "no version_num" as
    # "unpublished".
    parsed = tomlkit.parse(out)
    assert "version_num" not in parsed["entity"]["published"]
    assert "unpublished" in out  # comment text present in serialized form


def test_entity_toml_omits_draft_when_none() -> None:
    e = EntityRecord(
        can_stand_alone=True,
        key="xblock.v1:problem:published-only",
        created=datetime(2025, 9, 4, 22, 37, 24, tzinfo=timezone.utc),
        versions=[EntityVersionRecord(title="P", version_num=3)],
        draft_version_num=None,
        published_version_num=3,
    )
    out = emit_entity_toml(e)
    parsed = tomlkit.parse(out)
    # draft subtable absent
    assert "draft" not in parsed["entity"]
    # published still emits its version_num
    assert parsed["entity"]["published"]["version_num"] == 3


def test_entity_toml_multiple_versions() -> None:
    e = EntityRecord(
        can_stand_alone=True,
        key="xblock.v1:html:ml",
        created=datetime(2025, 9, 4, 22, 37, 24, tzinfo=timezone.utc),
        versions=[
            EntityVersionRecord(title="v1", version_num=1),
            EntityVersionRecord(title="v2", version_num=2),
        ],
        draft_version_num=2,
        published_version_num=1,
    )
    out = emit_entity_toml(e)
    parsed = tomlkit.parse(out)
    versions = parsed["version"]
    assert [v["version_num"] for v in versions] == [1, 2]
    assert [v["title"] for v in versions] == ["v1", "v2"]


# --- entity TOML — containers ---------------------------------------------


def test_entity_toml_section_container() -> None:
    e = EntityRecord(
        can_stand_alone=True,
        key="section1-8ca126",
        created=datetime(2025, 9, 4, 22, 37, 24, tzinfo=timezone.utc),
        versions=[EntityVersionRecord(title="Section 1", version_num=1)],
        draft_version_num=1,
        published_version_num=1,
        container_kind="section",
    )
    out = emit_entity_toml(e)
    parsed = tomlkit.parse(out)
    # [entity.container.section] empty subtable present
    assert "container" in parsed["entity"]
    assert "section" in parsed["entity"]["container"]
    # subtable is empty
    assert dict(parsed["entity"]["container"]["section"]) == {}


def test_entity_toml_unit_container() -> None:
    e = EntityRecord(
        can_stand_alone=True,
        key="unit1-b7eafb",
        created=datetime(2025, 9, 4, 22, 37, 24, tzinfo=timezone.utc),
        versions=[EntityVersionRecord(title="Unit 1", version_num=1)],
        draft_version_num=1,
        published_version_num=1,
        container_kind="unit",
    )
    out = emit_entity_toml(e)
    parsed = tomlkit.parse(out)
    assert "unit" in parsed["entity"]["container"]


def test_entity_toml_no_versions() -> None:
    # Edge case: entity with no draft and no published. The fixture should
    # still parse, just with no [[version]] entries.
    e = EntityRecord(
        can_stand_alone=False,
        key="xblock.v1:problem:zombie",
        created=datetime(2025, 9, 4, 22, 37, 24, tzinfo=timezone.utc),
        versions=[],
        draft_version_num=None,
        published_version_num=None,
    )
    out = emit_entity_toml(e)
    parsed = tomlkit.parse(out)
    # tomlkit may not include "version" key at all when no AoT was added.
    assert parsed.get("version") in (None, [])


# --- collection TOML ------------------------------------------------------


def test_collection_toml_round_trips() -> None:
    c = CollectionRecord(
        title="Collection test1",
        key="collection-test",
        description="",
        created=datetime(2025, 8, 19, 4, 25, 27, 754968, tzinfo=timezone.utc),
        entity_keys=[
            "xblock.v1:html:e32d5479-9492-41f6-9222-550a7346bc37",
            "xblock.v1:problem:256739e8-c2df-4ced-bd10-8156f6cfa90b",
        ],
    )
    out = emit_collection_toml(c)
    parsed = tomlkit.parse(out)
    assert parsed["collection"]["title"] == "Collection test1"
    assert parsed["collection"]["key"] == "collection-test"
    assert parsed["collection"]["description"] == ""
    assert list(parsed["collection"]["entities"]) == c.entity_keys


def test_collection_toml_empty_entities() -> None:
    c = CollectionRecord(
        title="Empty",
        key="empty",
        description="",
        created=datetime(2025, 8, 19, 4, 25, 27, 754968, tzinfo=timezone.utc),
        entity_keys=[],
    )
    out = emit_collection_toml(c)
    parsed = tomlkit.parse(out)
    assert list(parsed["collection"]["entities"]) == []


def test_collection_toml_preserves_entity_order() -> None:
    c = CollectionRecord(
        title="Ordered",
        key="o",
        description="",
        created=datetime(2025, 8, 19, 4, 25, 27, 754968, tzinfo=timezone.utc),
        entity_keys=["c", "a", "b"],
    )
    out = emit_collection_toml(c)
    parsed = tomlkit.parse(out)
    assert list(parsed["collection"]["entities"]) == ["c", "a", "b"]
