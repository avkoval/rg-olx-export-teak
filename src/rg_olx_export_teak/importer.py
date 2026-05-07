"""Import an openedx-core archive zip into openedx-learning 0.26.

The inverse of ``exporter.py``. Reads a zip produced by ``export_lp`` (or by
openedx-core 0.45+'s LearningPackageZipper, since the on-disk layout is
shared) and writes its contents into a teak-era openedx-learning database.

What this command does
----------------------

1. Parse ``package.toml`` → ensure the target ``LearningPackage`` exists
   (idempotent: same key reuses, different key creates).
2. For each ``entities/<ns>/<type>/<slug>.toml``:

   - resolve / create the ``ComponentType`` (e.g. ``xblock.v1/problem``);
   - resolve / create the ``Component`` keyed by ``local_key = slug``;
   - for each ``component_versions/v<N>/`` directory in the zip, build a
     ``ComponentVersion`` whose content map is keyed by the path-in-version
     (``block.xml``, ``static/foo.png``, ...). Use the published version
     listed in the entity TOML; draft is currently ignored to keep v0 lean.

3. For each ``collections/<slug>.toml``: get-or-create the Collection and
   reset its membership to the listed entity keys.

What this command does NOT do (yet)
-----------------------------------

- *Containers* (sections / subsections / units) are skipped with a warning.
  v2 Libraries — our primary use case — don't use containers; courses do.
  Re-creating containers needs the openedx_learning container API which
  has churn between 0.26 and 0.45.
- *Tag re-creation*. ``<meta>`` blocks emitted by the exporter are stripped
  from ``block.xml`` on import (otherwise Studio renders them literally).
  Re-creating ``ObjectTag`` rows requires a Taxonomy lookup chain that
  differs between teak and ulmo; do that in a follow-up.
- *Static assets / media files*. Stored as ``ComponentVersionContent`` rows
  but Studio's serving path for v2 Library static assets is still in flux
  in teak. Round-trip (export → import → re-export) preserves bytes; live
  rendering of images may need the ``mfe_meili_keys`` style of patch.

Idempotency
-----------

Re-running the same zip is safe:

- LearningPackage with the same key is reused (title/description updated).
- Component with the same ``local_key`` reuses the row; a new
  ``ComponentVersion`` is appended only if its content differs from the
  current published version. (The publish action is a no-op if nothing
  changed.)
- Collection membership is *replaced* with the zip's manifest, not merged.

This matches ``export_lp``'s round-trip-stable behaviour.
"""
from __future__ import annotations

import logging
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any

from openedx_learning.api import authoring as authoring_api
from openedx_learning.apps.authoring.collections.models import Collection
from openedx_learning.apps.authoring.components.models import ComponentType
from openedx_learning.apps.authoring.publishing.models import (
    LearningPackage,
    PublishableEntity,
)

from .records import (
    CollectionRecord,
    EntityRecord,
    LearningPackageRecord,
)
from .toml_parse import (
    parse_collection_toml,
    parse_entity_toml,
    parse_package_toml,
    TomlParseError,
)

log = logging.getLogger(__name__)


PACKAGE_TOML = "package.toml"
BLOCK_XML_KEY = "block.xml"
ENTITIES_PREFIX = "entities/"
COLLECTIONS_PREFIX = "collections/"

# Strip the export-injected <meta>...</meta> block from problem block.xml
# before storing. We don't recreate ObjectTags here; that's a follow-up.
META_BLOCK_RE = re.compile(r"<meta>.*?</meta>\s*", flags=re.DOTALL)


@dataclass
class ImportResult:
    """Summary of one import run, returned to the caller (CLI prints it)."""

    learning_package_key: str
    learning_package_id: int
    num_components_created: int = 0
    num_components_updated: int = 0
    num_versions_written: int = 0
    num_static_files: int = 0
    num_collections_created: int = 0
    num_collections_updated: int = 0
    skipped_containers: list[str] = field(default_factory=list)
    skipped_entities: list[tuple[str, str]] = field(default_factory=list)


class ImportFormatError(Exception):
    """The zip is not a recognisable openedx-core archive."""


def import_learning_package(
    zip_path: str,
    *,
    override_lp_key: str | None = None,
    publish: bool = True,
) -> ImportResult:
    """Read ``zip_path`` and write its contents into the local DB.

    ``override_lp_key`` lets the caller install the package under a key
    different from the one in ``package.toml``. Useful for parallel imports
    of two snapshots of the same source LP for diffing.

    ``publish``: if True, every component version we created is published
    in a single ``publish_all_drafts`` call at the end. If False, versions
    land as drafts only — useful for previewing in Studio without exposing
    them to the LMS.
    """
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())
        if PACKAGE_TOML not in names:
            raise ImportFormatError(
                f"{zip_path}: missing {PACKAGE_TOML} — not an openedx-core archive"
            )

        lp_record, _context = parse_package_toml(zf.read(PACKAGE_TOML).decode("utf-8"))
        lp_key = override_lp_key or lp_record.key
        lp = _ensure_learning_package(lp_key, lp_record)

        result = ImportResult(
            learning_package_key=lp_key,
            learning_package_id=lp.id,
        )

        log.info(
            "Importing LP %s (%s) from %s",
            lp.id, lp_key, zip_path,
        )

        entity_tomls = sorted(n for n in names if _is_entity_toml(n))
        for name in entity_tomls:
            try:
                _import_one_entity(zf, name, lp, result)
            except Exception as exc:  # noqa: BLE001 — we want a report, not a crash
                log.warning("Failed to import %s: %s", name, exc)
                result.skipped_entities.append((name, str(exc)))

        collection_tomls = sorted(n for n in names if _is_collection_toml(n))
        for name in collection_tomls:
            _import_one_collection(zf, name, lp, result)

    if publish and result.num_versions_written > 0:
        authoring_api.publish_all_drafts(
            lp.id,
            message=f"Imported from {zip_path}",
            published_at=datetime.now(tz=timezone.utc),
        )

    log.info(
        "Done. components=+%s/~%s versions=%s collections=+%s/~%s static=%s skipped=%s",
        result.num_components_created, result.num_components_updated,
        result.num_versions_written,
        result.num_collections_created, result.num_collections_updated,
        result.num_static_files, len(result.skipped_entities),
    )
    return result


# --- LP / entity / collection helpers -----------------------------------------


def _ensure_learning_package(
    lp_key: str,
    record: LearningPackageRecord,
) -> LearningPackage:
    try:
        lp = LearningPackage.objects.get(key=lp_key)
        # Refresh title/description from the zip; key is the stable handle.
        dirty = False
        if lp.title != record.title:
            lp.title = record.title
            dirty = True
        if (lp.description or "") != (record.description or ""):
            lp.description = record.description
            dirty = True
        if dirty:
            lp.save(update_fields=["title", "description"])
        return lp
    except LearningPackage.DoesNotExist:
        return authoring_api.create_learning_package(
            key=lp_key,
            title=record.title,
            description=record.description,
        )


def _import_one_entity(
    zf: zipfile.ZipFile,
    toml_name: str,
    lp: LearningPackage,
    result: ImportResult,
) -> None:
    """Read one ``entities/<ns>/<type>/<slug>.toml`` and write all its versions."""
    text = zf.read(toml_name).decode("utf-8")
    record = parse_entity_toml(text)

    namespace, type_name, slug = _parse_entity_path(toml_name)
    if namespace is None:
        # Container TOML at entities/<slug>.toml — defer to follow-up work.
        result.skipped_containers.append(record.key)
        log.info("Skipping container %s (containers not yet supported)", record.key)
        return

    component, was_created = _ensure_component(
        lp=lp,
        namespace=namespace,
        type_name=type_name,
        slug=slug,
        record=record,
    )
    if was_created:
        result.num_components_created += 1
    else:
        result.num_components_updated += 1

    for v in record.versions:
        version_dir = (
            f"entities/{namespace}/{type_name}/{slug}/component_versions/v{v.version_num}/"
        )
        version_files = sorted(
            n for n in zf.namelist() if n.startswith(version_dir) and not n.endswith("/")
        )
        if not version_files:
            log.debug("No payload files for %s v%s; skipping", record.key, v.version_num)
            continue

        _write_version(
            zf=zf,
            component=component,
            version_dir=version_dir,
            version_files=version_files,
            title=v.title,
            type_name=type_name,
            result=result,
        )


def _ensure_component(
    *,
    lp: LearningPackage,
    namespace: str,
    type_name: str,
    slug: str,
    record: EntityRecord,
) -> tuple[Any, bool]:
    """Get-or-create the ``Component`` row for this entity.

    Returns ``(component, created)``. Idempotent across re-imports.
    """
    component_type, _ = ComponentType.objects.get_or_create(
        namespace=namespace,
        name=type_name,
    )

    # The PublishableEntity.key for a component follows
    # "<namespace>:<type>:<slug>" — match the export's behaviour by checking
    # the entity record's key first, then falling back to slug-based lookup.
    try:
        entity = PublishableEntity.objects.select_related("component").get(
            learning_package_id=lp.id, key=record.key,
        )
        return entity.component, False
    except PublishableEntity.DoesNotExist:
        pass

    component = authoring_api.create_component(
        learning_package_id=lp.id,
        component_type=component_type,
        local_key=slug,
        created=record.created,
    )
    return component, True


def _write_version(
    *,
    zf: zipfile.ZipFile,
    component: Any,
    version_dir: str,
    version_files: list[str],
    title: str,
    type_name: str,
    result: ImportResult,
) -> None:
    """Write one ComponentVersion's content map from the zip."""
    content_to_replace: dict[str, int] = {}
    now = datetime.now(tz=timezone.utc)

    for path_in_zip in version_files:
        path_in_version = path_in_zip[len(version_dir):]
        payload = zf.read(path_in_zip)

        mime_type = _guess_mime(path_in_version, type_name)

        if path_in_version == BLOCK_XML_KEY:
            text = payload.decode("utf-8")
            text = META_BLOCK_RE.sub("", text, count=1)
            content, _ = authoring_api.get_or_create_text_content(
                learning_package_id=component.learning_package_id,
                mime_type=mime_type,
                text=text,
                created=now,
            )
        else:
            content, _ = authoring_api.get_or_create_file_content(
                learning_package_id=component.learning_package_id,
                mime_type=mime_type,
                data=payload,
                created=now,
            )
            result.num_static_files += 1

        content_to_replace[path_in_version] = content.pk

    authoring_api.create_next_component_version(
        component_pk=component.pk,
        title=title or component.local_key,
        content_to_replace=content_to_replace,
        created=now,
    )
    result.num_versions_written += 1


def _import_one_collection(
    zf: zipfile.ZipFile,
    toml_name: str,
    lp: LearningPackage,
    result: ImportResult,
) -> None:
    text = zf.read(toml_name).decode("utf-8")
    record: CollectionRecord = parse_collection_toml(text)

    try:
        collection = Collection.objects.get(learning_package_id=lp.id, key=record.key)
        if collection.title != record.title:
            collection.title = record.title
            collection.save(update_fields=["title"])
        if (collection.description or "") != (record.description or ""):
            collection.description = record.description
            collection.save(update_fields=["description"])
        result.num_collections_updated += 1
    except Collection.DoesNotExist:
        collection = authoring_api.create_collection(
            learning_package_id=lp.id,
            key=record.key,
            title=record.title,
            description=record.description,
        )
        result.num_collections_created += 1

    # Reset membership to the zip's manifest. Entity keys missing from the LP
    # are silently skipped — they may belong to a sibling LP or have been
    # filtered out (e.g. invalid problems with --allow-invalid in export).
    entities = list(
        PublishableEntity.objects.filter(
            learning_package_id=lp.id, key__in=record.entity_keys,
        )
    )
    collection.entities.set(entities)


# --- path / mime helpers ------------------------------------------------------


def _is_entity_toml(name: str) -> bool:
    if not name.startswith(ENTITIES_PREFIX) or not name.endswith(".toml"):
        return False
    return "/component_versions/" not in name


def _is_collection_toml(name: str) -> bool:
    return name.startswith(COLLECTIONS_PREFIX) and name.endswith(".toml")


def _parse_entity_path(toml_name: str) -> tuple[str | None, str | None, str | None]:
    """Return ``(namespace, type_name, slug)`` for component TOMLs, ``(None, None, None)`` for containers.

    Component layout:  ``entities/<ns>/<type>/<slug>.toml``
    Container layout:  ``entities/<slug>.toml``
    """
    parts = PurePosixPath(toml_name).parts
    if len(parts) == 4 and parts[0] == "entities":
        namespace, type_name, fname = parts[1], parts[2], parts[3]
        return namespace, type_name, fname[: -len(".toml")]
    return None, None, None


def _guess_mime(path_in_version: str, type_name: str) -> str:
    """Best-effort MIME for a content payload.

    Specialises the canonical ``block.xml`` filename to the matching XBlock
    XML media type so Studio's content discovery treats it correctly. Other
    files fall through to ``mimetypes`` and finally to octet-stream.
    """
    if path_in_version == BLOCK_XML_KEY:
        return f"application/vnd.openedx.xblock.v1.{type_name}+xml"

    import mimetypes
    guess, _ = mimetypes.guess_type(path_in_version)
    return guess or "application/octet-stream"
