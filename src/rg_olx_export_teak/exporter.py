"""Export a v2 LearningPackage from openedx-learning 0.26 to an OLX zip.

The orchestrator that ties everything together:

1. ``package.toml`` from ``LearningPackage`` row.
2. For each ``PublishableEntity`` in the LP:

   - If it's a ``Component``, write ``entities/<ns>/<type>/<slug>.toml`` plus
     each version's ``component_versions/v<N>/...`` files.
   - If it's a ``Container``, write ``entities/<slug>.toml`` (no media).

3. For ``<problem>`` components, inject ``<meta>`` blocks into ``block.xml``
   from ``openedx_tagging.core.tagging.models.ObjectTag`` rows
   keyed on the ``PublishableEntity.uuid``.

4. ``collections/<slug>.toml`` for each enabled ``Collection``.

Imports of ``openedx_learning.*`` are at module top — this file is meant
to be imported only inside the LMS/CMS Tutor process where those models
exist. Unit-testing the orchestrator directly is therefore not in scope;
end-to-end tests run inside Tutor.
"""
from __future__ import annotations

import logging
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openedx_learning.apps.authoring.collections.models import Collection
from openedx_learning.apps.authoring.publishing.models import (
    LearningPackage,
    PublishableEntity,
)

from ._filename import FilenameAllocator
from .meta_xml import inject_meta_block
from .records import (
    CollectionRecord,
    EntityRecord,
    EntityVersionRecord,
    ExportContext,
    LearningPackageRecord,
)
from .tag_query import component_usage_key, tag_groups_for_object_id
from .toml_emit import emit_collection_toml, emit_entity_toml, emit_package_toml

log = logging.getLogger(__name__)


XBLOCK_NAMESPACE = "xblock.v1"
PROBLEM_TYPE_NAME = "problem"
BLOCK_XML_KEY = "block.xml"
CONTAINER_KINDS = ("section", "subsection", "unit")


@dataclass
class ExportResult:
    """Summary of one export run, returned to the caller (CLI prints it)."""

    learning_package_key: str
    output_path: Path
    num_components: int = 0
    num_containers: int = 0
    num_collections: int = 0
    num_problems_with_meta: int = 0
    num_static_files: int = 0
    skipped_entities: list[str] = field(default_factory=list)


def export_learning_package(
    learning_package_id: int,
    output_path: str | Path,
    *,
    context: ExportContext,
) -> ExportResult:
    """Walk LP and write a zip at ``output_path``. Returns a summary."""
    lp = LearningPackage.objects.get(id=learning_package_id)
    output_path = Path(output_path)

    lp_record = LearningPackageRecord(
        title=lp.title,
        key=lp.key,
        description=lp.description,
        created=lp.created,
        updated=lp.updated,
    )

    allocator = FilenameAllocator()
    result = ExportResult(
        learning_package_key=lp.key,
        output_path=output_path,
    )

    log.info(
        "Starting export of LearningPackage id=%s key=%s -> %s",
        learning_package_id, lp.key, output_path,
    )

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
        _write_text(zipf, "package.toml", emit_package_toml(lp_record, context), lp.updated)

        entities = (
            PublishableEntity.objects
            .filter(learning_package_id=learning_package_id)
            .select_related(
                "component",
                "component__component_type",
                "container",
            )
            .order_by("key")
        )

        for entity in entities:
            if hasattr(entity, "component"):
                _emit_component(zipf, entity, allocator, lp.updated, result, lp.key)
            elif hasattr(entity, "container"):
                _emit_container(zipf, entity, allocator, lp.updated, result)
            else:
                log.warning(
                    "Skipping entity key=%s uuid=%s — neither component nor container",
                    entity.key, entity.uuid,
                )
                result.skipped_entities.append(entity.key)

        collections = Collection.objects.filter(
            learning_package_id=learning_package_id,
            enabled=True,
        )
        for collection in collections:
            _emit_collection(zipf, collection, allocator, result)

    log.info(
        "Done. components=%s containers=%s collections=%s problems_with_meta=%s static_files=%s",
        result.num_components, result.num_containers, result.num_collections,
        result.num_problems_with_meta, result.num_static_files,
    )
    return result


# --- per-entity emitters ------------------------------------------------------


def _emit_component(
    zipf: zipfile.ZipFile,
    entity: PublishableEntity,
    allocator: FilenameAllocator,
    fallback_ts: Any,
    result: ExportResult,
    learning_package_key: str,
) -> None:
    component = entity.component
    component_type = component.component_type
    namespace = component_type.namespace
    type_name = component_type.name

    slug = allocator.allocate(component.local_key)
    component_root = f"entities/{namespace}/{type_name}"

    versions_to_write, draft_v_num, published_v_num = _versions_to_write(component)

    record = EntityRecord(
        can_stand_alone=entity.can_stand_alone,
        key=entity.key,
        created=entity.created,
        versions=[
            EntityVersionRecord(
                title=cv.publishable_entity_version.title,
                version_num=cv.publishable_entity_version.version_num,
            )
            for cv in versions_to_write
        ],
        draft_version_num=draft_v_num,
        published_version_num=published_v_num,
    )

    _write_text(
        zipf, f"{component_root}/{slug}.toml",
        emit_entity_toml(record), fallback_ts,
    )

    is_problem = (namespace == XBLOCK_NAMESPACE and type_name == PROBLEM_TYPE_NAME)
    if not versions_to_write:
        return
    result.num_components += 1

    for cv in versions_to_write:
        v_num = cv.publishable_entity_version.version_num
        v_ts = cv.publishable_entity_version.created
        v_dir = f"{component_root}/{slug}/component_versions/v{v_num}"

        for cvc in cv.componentversioncontent_set.select_related("content", "content__media_type").all():
            path_in_version = cvc.key  # e.g. "block.xml" or "static/me.png"
            payload = _read_content_payload(cvc.content)
            if payload is None:
                continue

            if is_problem and path_in_version == BLOCK_XML_KEY:
                # edx-platform's content_tagging keys ObjectTag rows by
                # the v2 Library UsageKey (lb:<org>:<slug>:<type>:<local_key>),
                # not by PublishableEntity.uuid. See tag_query.component_usage_key.
                usage_key = component_usage_key(
                    learning_package_key, type_name, component.local_key,
                )
                groups = tag_groups_for_object_id(usage_key)
                if groups:
                    text = payload if isinstance(payload, str) else payload.decode("utf-8")
                    payload = inject_meta_block(text, groups)
                    result.num_problems_with_meta += 1

            _write_blob(zipf, f"{v_dir}/{path_in_version}", payload, v_ts)

            if path_in_version != BLOCK_XML_KEY:
                result.num_static_files += 1


def _emit_container(
    zipf: zipfile.ZipFile,
    entity: PublishableEntity,
    allocator: FilenameAllocator,
    fallback_ts: Any,
    result: ExportResult,
) -> None:
    container = entity.container
    kind = _container_kind(container)
    slug = allocator.allocate(entity.key)

    versions_to_write, draft_v_num, published_v_num = _versions_to_write(container)

    record = EntityRecord(
        can_stand_alone=entity.can_stand_alone,
        key=entity.key,
        created=entity.created,
        versions=[
            EntityVersionRecord(
                title=cv.publishable_entity_version.title,
                version_num=cv.publishable_entity_version.version_num,
            )
            for cv in versions_to_write
        ],
        draft_version_num=draft_v_num,
        published_version_num=published_v_num,
        container_kind=kind,
    )
    _write_text(zipf, f"entities/{slug}.toml", emit_entity_toml(record), fallback_ts)
    result.num_containers += 1


def _emit_collection(
    zipf: zipfile.ZipFile,
    collection: Collection,
    allocator: FilenameAllocator,
    result: ExportResult,
) -> None:
    slug = allocator.allocate(collection.key)
    entity_keys = list(
        collection.entities.order_by("key").values_list("key", flat=True)
    )
    record = CollectionRecord(
        title=collection.title,
        key=collection.key,
        description=collection.description,
        created=collection.created,
        entity_keys=entity_keys,
    )
    _write_text(
        zipf, f"collections/{slug}.toml",
        emit_collection_toml(record), collection.modified,
    )
    result.num_collections += 1


# --- helpers ------------------------------------------------------------------


def _versions_to_write(content_obj: Any) -> tuple[list[Any], int | None, int | None]:
    """Return ``(versions_to_write, draft_num, published_num)``.

    Mirrors openedx-core 0.45 zipper's behaviour: draft first, then published
    if it differs. Either may be ``None``.
    """
    versioning = content_obj.versioning
    draft = versioning.draft
    published = versioning.published

    versions: list[Any] = []
    if draft is not None:
        versions.append(draft)
    if published is not None and published != draft:
        versions.append(published)

    draft_num = (
        draft.publishable_entity_version.version_num if draft is not None else None
    )
    published_num = (
        published.publishable_entity_version.version_num if published is not None else None
    )
    return versions, draft_num, published_num


def _container_kind(container: Any) -> str | None:
    """Return ``"section"`` / ``"subsection"`` / ``"unit"`` or ``None``."""
    for kind in CONTAINER_KINDS:
        if hasattr(container, kind):
            return kind
    return None


def _read_content_payload(content: Any) -> str | bytes | None:
    """Return the textual or binary payload of a ``Content`` row.

    ``Content`` may store text (``content.text``), a file
    (``content.has_file`` + ``content.read_file()``), or both. Prefer text
    when available — it's cheaper and avoids storage round-trips. Falls
    back to file. Returns ``None`` if neither is set or the file read fails.
    """
    if content.text:
        return content.text
    if getattr(content, "has_file", False):
        try:
            with content.read_file() as fh:
                return fh.read()
        except Exception as exc:  # noqa: BLE001 — best-effort; we log + skip
            log.warning(
                "Failed to read file payload for content id=%s: %s",
                getattr(content, "id", "?"), exc,
            )
            return None
    return None


def _write_text(
    zipf: zipfile.ZipFile,
    path: str,
    text: str,
    timestamp: Any,
) -> None:
    info = zipfile.ZipInfo(path)
    info.date_time = timestamp.timetuple()[:6]
    info.compress_type = zipfile.ZIP_DEFLATED
    zipf.writestr(info, text.encode("utf-8"))


def _write_blob(
    zipf: zipfile.ZipFile,
    path: str,
    data: str | bytes,
    timestamp: Any,
) -> None:
    info = zipfile.ZipInfo(path)
    info.date_time = timestamp.timetuple()[:6]
    info.compress_type = zipfile.ZIP_DEFLATED
    if isinstance(data, str):
        data = data.encode("utf-8")
    zipf.writestr(info, data)
