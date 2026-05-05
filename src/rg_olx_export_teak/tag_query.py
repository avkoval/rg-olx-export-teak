"""Tag lookups for the deep-path ``openedx_tagging.core.tagging.models``.

edx-platform release/teak (and most pre-openedx-core deployments) ship
``openedx_tagging`` in its *deep* layout — ``openedx_tagging.core.tagging.*``.
Our openedx-core fork ships the *flat* layout — ``openedx_tagging.*``. The
two cannot coexist in one ``sys.path``. This module imports the deep
form, which is what the Tutor LMS/CMS process has installed.

Identifier shape: edx-platform's ``content_tagging`` app attaches tags
to v2 Library components using the v2 Library *UsageKey* string, e.g.
``lb:KSK:test-lib:problem:<local_key>``. This is **not**
``PublishableEntity.uuid``. The ``content_tagging`` API derives the
``lb:`` prefix from the LP key (``lib:`` → ``lb:``).

The pure helper ``extract_tag_groups`` is the format-stable boundary —
unit-tested without Django. ``tag_groups_for_object_id`` wraps it with
the live ORM query. ``component_usage_key`` is the small pure helper
that builds the lookup id from the LP key + component type + local key.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Any


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


def component_usage_key(
    learning_package_key: str,
    component_type_name: str,
    local_key: str,
) -> str:
    """Build the v2-Library UsageKey string used by ``content_tagging``.

    edx-platform constructs the lookup id by stripping the ``lib:``
    prefix from the LearningPackage key and prefixing ``lb:``, then
    appending the block type and local key. Example::

        learning_package_key = "lib:KSK:test-lib"
        component_type_name  = "problem"
        local_key            = "abc-123"
        result               = "lb:KSK:test-lib:problem:abc-123"
    """
    if learning_package_key.startswith("lib:"):
        lib_part = learning_package_key[len("lib:"):]
    else:
        # Defensive: if some non-v2-Library LP slipped in, keep the key
        # verbatim. Such rows almost certainly have no tags anyway.
        lib_part = learning_package_key
    return f"lb:{lib_part}:{component_type_name}:{local_key}"


def tag_groups_for_object_id(object_id: str) -> dict[str, list[str]]:
    """Return ``{taxonomy_export_id: [value, ...]}`` for one ``object_id``.

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
        .filter(object_id=object_id)
        .select_related("taxonomy")
        .order_by("taxonomy__export_id", "_value")
    )
    return extract_tag_groups(qs)
