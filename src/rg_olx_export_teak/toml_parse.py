"""TOML parsers for the openedx-core archive format (inverse of ``toml_emit``).

Three TOML kinds, each parsed into the same records ``toml_emit`` produces:

- ``package.toml`` → (LearningPackageRecord, ImportContext)
- ``entities/<...>.toml`` → EntityRecord
- ``collections/<slug>.toml`` → CollectionRecord

These functions are pure: in string → out records. No Django, no DB.
The caller is the importer orchestrator (``importer.py``).

Robustness: missing optional fields (created_by, description, etc.) are
tolerated. Mandatory fields raise ``TomlParseError`` so a bad zip fails
loudly *before* any DB writes happen.
"""
from __future__ import annotations

from datetime import datetime, timezone

import tomlkit

from .records import (
    CollectionRecord,
    EntityRecord,
    EntityVersionRecord,
    ExportContext,
    LearningPackageRecord,
)


class TomlParseError(ValueError):
    """A required field is missing or has the wrong shape."""


def parse_package_toml(text: str) -> tuple[LearningPackageRecord, ExportContext]:
    """Inverse of ``emit_package_toml``."""
    doc = tomlkit.parse(text)
    meta = _table(doc, "meta")
    lp = _table(doc, "learning_package")

    return (
        LearningPackageRecord(
            title=_required_str(lp, "title", "learning_package.title"),
            key=_required_str(lp, "key", "learning_package.key"),
            description=_optional_str(lp, "description", default=""),
            created=_required_datetime(lp, "created", "learning_package.created"),
            updated=_required_datetime(lp, "updated", "learning_package.updated"),
        ),
        ExportContext(
            created_at=_required_datetime(meta, "created_at", "meta.created_at"),
            created_by=_optional_str(meta, "created_by"),
            created_by_email=_optional_str(meta, "created_by_email"),
            origin_server=_optional_str(meta, "origin_server"),
            format_version=int(meta.get("format_version", 1)),
        ),
    )


def parse_entity_toml(text: str) -> EntityRecord:
    """Inverse of ``emit_entity_toml``. Handles both components and containers."""
    doc = tomlkit.parse(text)
    entity = _table(doc, "entity")

    draft_v = None
    if "draft" in entity:
        draft_v = int(entity["draft"]["version_num"])

    published_v = None
    published = entity.get("published")
    # An unpublished entity has either no [entity.published] table at all, or
    # a table whose only content is the "unpublished" comment (no version_num).
    if published is not None and "version_num" in published:
        published_v = int(published["version_num"])

    container_kind = None
    container = entity.get("container")
    if container is not None:
        for kind in ("section", "subsection", "unit"):
            if kind in container:
                container_kind = kind
                break

    versions: list[EntityVersionRecord] = []
    for v in doc.get("version", []) or []:
        versions.append(EntityVersionRecord(
            title=str(v.get("title", "")),
            version_num=int(v["version_num"]),
        ))

    return EntityRecord(
        can_stand_alone=bool(entity.get("can_stand_alone", True)),
        key=_required_str(entity, "key", "entity.key"),
        created=_required_datetime(entity, "created", "entity.created"),
        versions=versions,
        draft_version_num=draft_v,
        published_version_num=published_v,
        container_kind=container_kind,
    )


def parse_collection_toml(text: str) -> CollectionRecord:
    """Inverse of ``emit_collection_toml``."""
    doc = tomlkit.parse(text)
    collection = _table(doc, "collection")
    entities = list(collection.get("entities") or [])
    return CollectionRecord(
        title=_required_str(collection, "title", "collection.title"),
        key=_required_str(collection, "key", "collection.key"),
        description=_optional_str(collection, "description", default=""),
        created=_required_datetime(collection, "created", "collection.created"),
        entity_keys=[str(k) for k in entities],
    )


# --- helpers ------------------------------------------------------------------


def _table(doc, name: str):
    table = doc.get(name)
    if table is None:
        raise TomlParseError(f"missing top-level table [{name}]")
    return table


def _required_str(table, key: str, dotted: str) -> str:
    if key not in table:
        raise TomlParseError(f"missing required field {dotted}")
    return str(table[key])


def _optional_str(table, key: str, default: str | None = None) -> str | None:
    if key not in table:
        return default
    val = table[key]
    return str(val) if val is not None else default


def _required_datetime(table, key: str, dotted: str) -> datetime:
    if key not in table:
        raise TomlParseError(f"missing required field {dotted}")
    val = table[key]
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    raise TomlParseError(f"{dotted} is not a datetime: {val!r}")
