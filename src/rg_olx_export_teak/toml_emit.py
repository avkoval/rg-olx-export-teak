"""TOML emitters for the openedx-core archive format.

Three TOML kinds, all written verbatim into the zip by the exporter:

- ``package.toml`` — one per archive
- ``entities/<...>.toml`` — one per ``PublishableEntity``
- ``collections/<slug>.toml`` — one per ``Collection``

The output matches openedx-core 0.45's fixture
(``tests/openedx_content/applets/backup_restore/fixtures/library_backup/``
in the upstream openedx-core repo) byte-for-byte at the structural level
so its ``LearningPackageUnzipper`` can ingest our zips. Field naming on
disk uses ``key`` everywhere (``LearningPackage``, ``PublishableEntity``,
``Collection``) — a deliberate stability decision in upstream that hides
the 0.26 → 0.45 Python field rename.

See ``docs/FORMAT.md`` for the full spec.

These functions are pure: in records → out string. No Django, no DB.
"""
from __future__ import annotations

import tomlkit

from .records import (
    CollectionRecord,
    EntityRecord,
    ExportContext,
    LearningPackageRecord,
)


def emit_package_toml(
    learning_package: LearningPackageRecord,
    context: ExportContext,
) -> str:
    """Build the ``package.toml`` content. ``[meta]`` is emitted first."""
    doc = tomlkit.document()

    meta = tomlkit.table()
    meta.add("format_version", context.format_version)
    if context.created_by is not None:
        meta.add("created_by", context.created_by)
    if context.created_by_email is not None:
        meta.add("created_by_email", context.created_by_email)
    meta.add("created_at", context.created_at)
    if context.origin_server is not None:
        meta.add("origin_server", context.origin_server)

    lp = tomlkit.table()
    lp.add("title", learning_package.title)
    lp.add("key", learning_package.key)
    lp.add("description", learning_package.description)
    lp.add("created", learning_package.created)
    lp.add("updated", learning_package.updated)

    doc.add("meta", meta)
    doc.add("learning_package", lp)
    return tomlkit.dumps(doc)


def emit_entity_toml(entity: EntityRecord) -> str:
    """Build a single entity TOML (component or container).

    Format:

        [entity]
        can_stand_alone = ...
        key = "..."
        created = TIMESTAMP

        [entity.draft]
        version_num = N

        [entity.published]
        version_num = N    # OR `# unpublished: no published_version_num`

        [entity.container.<kind>]    # only for containers

        # ### Versions

        [[version]]
        title = "..."
        version_num = N
    """
    doc = tomlkit.document()

    entity_table = tomlkit.table()
    entity_table.add("can_stand_alone", entity.can_stand_alone)
    entity_table.add("key", entity.key)
    entity_table.add("created", entity.created)

    if entity.draft_version_num is not None:
        draft = tomlkit.table()
        draft.add("version_num", entity.draft_version_num)
        entity_table.add("draft", draft)

    published = tomlkit.table()
    if entity.published_version_num is not None:
        published.add("version_num", entity.published_version_num)
    else:
        published.add(tomlkit.comment("unpublished: no published_version_num"))
    entity_table.add("published", published)

    if entity.container_kind is not None:
        container_table = tomlkit.table()
        container_table.add(entity.container_kind, tomlkit.table())
        entity_table.add("container", container_table)

    doc.add("entity", entity_table)

    doc.add(tomlkit.nl())
    doc.add(tomlkit.comment("### Versions"))
    for version in entity.versions:
        aot = tomlkit.aot()
        version_table = tomlkit.table()
        version_table.add("title", version.title)
        version_table.add("version_num", version.version_num)
        aot.append(version_table)
        doc.add("version", aot)

    return tomlkit.dumps(doc)


def emit_collection_toml(collection: CollectionRecord) -> str:
    """Build a ``collections/<slug>.toml`` file.

    Entity keys are emitted in the order supplied by the caller. Multi-line
    array formatting matches the openedx-core reference for readability.
    """
    doc = tomlkit.document()

    entities_array = tomlkit.array()
    entities_array.extend(collection.entity_keys)
    entities_array.multiline(True)

    table = tomlkit.table()
    table.add("title", collection.title)
    table.add("key", collection.key)
    table.add("description", collection.description)
    table.add("created", collection.created)
    table.add("entities", entities_array)

    doc.add("collection", table)
    return tomlkit.dumps(doc)
