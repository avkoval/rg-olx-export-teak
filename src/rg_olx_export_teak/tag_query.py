"""Tag lookups for the deep-path ``openedx_tagging.core.tagging.models``.

edx-platform release/teak (and most pre-openedx-core deployments) ship
``openedx_tagging`` in its *deep* layout — ``openedx_tagging.core.tagging.*``.
Our openedx-core fork ships the *flat* layout — ``openedx_tagging.*``. The
two cannot coexist in one ``sys.path``. This module imports the deep
form, which is what the Tutor LMS/CMS process has installed.

The pure helper ``extract_tag_groups`` is the format-stable boundary —
unit-tested without Django. ``tag_groups_for_entity`` wraps it with the
live ORM query.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Any
from uuid import UUID


def extract_tag_groups(
    object_tags: Iterable[Any],
) -> dict[str, list[str]]:
    """Group an iterable of ``ObjectTag``-like rows by ``taxonomy.export_id``.

    Each row must expose ``.taxonomy.export_id`` (str) and ``._value`` (str).
    Rows with empty ``export_id`` or empty ``_value`` are dropped.
    Duplicate ``(export_id, value)`` pairs are deduped while preserving the
    first-seen order within a taxonomy.
    """
    groups: dict[str, list[str]] = defaultdict(list)
    seen: dict[str, set[str]] = defaultdict(set)
    for row in object_tags:
        export_id = getattr(row.taxonomy, "export_id", None)
        if not export_id:
            continue
        value = getattr(row, "_value", None)
        if not value:
            continue
        if value in seen[export_id]:
            continue
        seen[export_id].add(value)
        groups[export_id].append(value)
    return dict(groups)


def tag_groups_for_entity(entity_uuid: UUID | str) -> dict[str, list[str]]:
    """Return ``{taxonomy_export_id: [value, ...]}`` for one PublishableEntity.

    Lazy-imports the ``ObjectTag`` model so the rest of this package can be
    imported (and unit-tested) without a Django environment that has the
    deep-path tagging app installed.
    """
    # Deep path — this is what edx-platform release/teak's INSTALLED_APPS
    # provides. The flat openedx-core path (`openedx_tagging.models`) is NOT
    # available in this runtime; trying it raises ModuleNotFoundError.
    from openedx_tagging.core.tagging.models import ObjectTag

    qs = (
        ObjectTag.objects
        .filter(object_id=str(entity_uuid))
        .select_related("taxonomy")
        .order_by("taxonomy__export_id", "_value")
    )
    return extract_tag_groups(qs)
