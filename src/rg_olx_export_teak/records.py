"""Plain data records that decouple TOML emission from Django models.

The exporter walks the Django ORM (``openedx_learning`` 0.26) and
constructs these dataclasses; the TOML emitters in ``toml_emit`` read
them. This keeps the format authority in one place and lets the emit
layer be unit-tested without Django.

Field naming follows the on-disk archive format (which uses ``key`` in
all three contexts). The 0.26 ORM happens to also use ``key`` for these
fields; the 0.45 fork renamed them in Python (``package_ref``,
``entity_ref``, ``collection_code``) but kept ``key`` on disk.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class ExportContext:
    """Operator-supplied metadata for the ``[meta]`` block of ``package.toml``."""

    created_at: datetime
    created_by: str | None = None  # username, optional
    created_by_email: str | None = None
    origin_server: str | None = None
    format_version: int = 1


@dataclass(frozen=True)
class LearningPackageRecord:
    """Source for the ``[learning_package]`` block of ``package.toml``."""

    title: str
    key: str
    description: str
    created: datetime
    updated: datetime


@dataclass(frozen=True)
class EntityVersionRecord:
    """One entry of the ``[[version]]`` AoT in an entity TOML."""

    title: str
    version_num: int


@dataclass(frozen=True)
class EntityRecord:
    """Source for an entity TOML — components and containers alike.

    ``draft_version_num`` and ``published_version_num`` may both be ``None``
    (no draft and never published) or one may be ``None`` (e.g. unpublished
    draft). ``versions`` lists the versions whose payloads are written into
    the zip (draft + published, deduped); the order matters for the AoT but
    is otherwise just informational.

    ``container_kind``: when the entity is a container, this carries one of
    ``"section"`` / ``"subsection"`` / ``"unit"`` so the emitter can write
    the ``[entity.container.<kind>]`` empty subtable. ``None`` for
    components.
    """

    can_stand_alone: bool
    key: str
    created: datetime
    versions: list[EntityVersionRecord] = field(default_factory=list)
    draft_version_num: int | None = None
    published_version_num: int | None = None
    container_kind: str | None = None


@dataclass(frozen=True)
class CollectionRecord:
    """Source for a single ``collections/<slug>.toml`` file."""

    title: str
    key: str
    description: str
    created: datetime
    entity_keys: list[str]
