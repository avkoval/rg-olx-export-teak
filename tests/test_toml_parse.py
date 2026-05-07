"""Round-trip tests for the TOML parsers.

Each test emits via ``toml_emit`` and parses back via ``toml_parse``,
asserting record equality. This guarantees the import side reads what
the export side writes — the central correctness property for round-trip.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

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
from rg_olx_export_teak.toml_parse import (
    parse_collection_toml,
    parse_entity_toml,
    parse_package_toml,
    TomlParseError,
)


def test_package_toml_round_trip() -> None:
    lp = LearningPackageRecord(
        title="Demo Library",
        key="lib:DemoX:ukr_law_2026",
        description="seeded by seed_demo_legal",
        created=datetime(2026, 5, 7, 3, 33, 0, tzinfo=timezone.utc),
        updated=datetime(2026, 5, 7, 3, 34, 0, tzinfo=timezone.utc),
    )
    ctx = ExportContext(
        created_at=datetime(2026, 5, 7, 3, 34, 5, tzinfo=timezone.utc),
        created_by="admin",
        created_by_email="admin@example.com",
        origin_server="studio.local.openedx.io",
    )
    text = emit_package_toml(lp, ctx)
    lp_parsed, ctx_parsed = parse_package_toml(text)

    assert lp_parsed == lp
    assert ctx_parsed.created_at == ctx.created_at
    assert ctx_parsed.created_by == ctx.created_by
    assert ctx_parsed.created_by_email == ctx.created_by_email
    assert ctx_parsed.origin_server == ctx.origin_server
    assert ctx_parsed.format_version == 1


def test_package_toml_missing_required_field() -> None:
    bad = """
[meta]
created_at = 2026-05-07T03:34:05Z

[learning_package]
title = "no key here"
description = ""
created = 2026-05-07T03:33:00Z
updated = 2026-05-07T03:34:00Z
"""
    with pytest.raises(TomlParseError, match="learning_package.key"):
        parse_package_toml(bad)


def test_entity_toml_round_trip_published() -> None:
    record = EntityRecord(
        can_stand_alone=True,
        key="xblock.v1:problem:demo_q1",
        created=datetime(2026, 5, 7, 3, 34, 0, tzinfo=timezone.utc),
        versions=[
            EntityVersionRecord(title="Q1", version_num=1),
            EntityVersionRecord(title="Q1 (revised)", version_num=2),
        ],
        draft_version_num=2,
        published_version_num=2,
    )
    text = emit_entity_toml(record)
    parsed = parse_entity_toml(text)
    assert parsed == record


def test_entity_toml_round_trip_unpublished() -> None:
    record = EntityRecord(
        can_stand_alone=True,
        key="xblock.v1:problem:demo_q2",
        created=datetime(2026, 5, 7, 3, 34, 0, tzinfo=timezone.utc),
        versions=[EntityVersionRecord(title="Draft", version_num=1)],
        draft_version_num=1,
        published_version_num=None,
    )
    text = emit_entity_toml(record)
    parsed = parse_entity_toml(text)
    assert parsed == record


def test_entity_toml_round_trip_container() -> None:
    record = EntityRecord(
        can_stand_alone=True,
        key="container:unit:demo_unit_1",
        created=datetime(2026, 5, 7, 3, 34, 0, tzinfo=timezone.utc),
        versions=[EntityVersionRecord(title="Unit 1", version_num=1)],
        draft_version_num=1,
        published_version_num=1,
        container_kind="unit",
    )
    text = emit_entity_toml(record)
    parsed = parse_entity_toml(text)
    assert parsed.container_kind == "unit"
    assert parsed == record


def test_collection_toml_round_trip() -> None:
    record = CollectionRecord(
        title="Базовий рівень",
        key="basic-level",
        description="питання базової складності",
        created=datetime(2026, 5, 7, 3, 34, 0, tzinfo=timezone.utc),
        entity_keys=["xblock.v1:problem:q1", "xblock.v1:problem:q2"],
    )
    text = emit_collection_toml(record)
    parsed = parse_collection_toml(text)
    assert parsed == record


def test_collection_toml_empty_entities() -> None:
    record = CollectionRecord(
        title="Empty",
        key="empty",
        description="",
        created=datetime(2026, 5, 7, 3, 34, 0, tzinfo=timezone.utc),
        entity_keys=[],
    )
    text = emit_collection_toml(record)
    parsed = parse_collection_toml(text)
    assert parsed.entity_keys == []
