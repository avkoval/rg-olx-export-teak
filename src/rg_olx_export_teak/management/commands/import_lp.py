"""Django management command: ``./manage.py import_lp <zip-path>``.

The import-side counterpart of ``export_lp``. Reads an openedx-core archive
zip (the format ``export_lp`` writes, also produced by openedx-core 0.45+'s
LearningPackageZipper) and writes its contents into the local
openedx-learning database.

Invocation inside a Tutor LMS or CMS container::

    tutor dev exec cms ./manage.py cms import_lp \\
        /tmp/demo.zip --library-key lib:DemoX:ukr_law_2026

After import, reindex Studio so the v2 Library tagging UI / Meilisearch
search picks up the new content::

    tutor dev exec cms ./manage.py cms reindex_studio --experimental --incremental

See ``src/rg_olx_export_teak/importer.py`` docstring for the full behaviour
(idempotency rules, what's deferred to follow-up work).
"""
from __future__ import annotations

import os

from django.core.management.base import BaseCommand, CommandError

from rg_olx_export_teak.importer import (
    import_learning_package,
    ImportFormatError,
)
from rg_olx_export_teak.toml_parse import TomlParseError


class Command(BaseCommand):
    help = (
        "Import an openedx-core archive zip into openedx-learning 0.26. "
        "Idempotent: re-running the same zip is safe. See README for "
        "limitations (containers and tag re-creation are deferred)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "zip_path",
            help="Path to the OLX archive zip *inside the container*.",
        )
        parser.add_argument(
            "--library-key",
            dest="library_key",
            default=None,
            help=(
                "Override the LearningPackage key from package.toml. "
                "Useful for parallel imports of two snapshots of the same "
                "source LP (e.g. for diffing). Default: use the key from "
                "package.toml."
            ),
        )
        parser.add_argument(
            "--no-publish",
            dest="publish",
            action="store_false",
            default=True,
            help=(
                "Land imported versions as drafts only — do not call "
                "publish_all_drafts. Default: publish."
            ),
        )
        parser.add_argument(
            "--no-apply-tags",
            dest="apply_tags",
            action="store_false",
            default=True,
            help=(
                "Skip ObjectTag re-creation from <meta> blocks. Tags are "
                "still stripped from block.xml so the renderer doesn't "
                "show them as text — this only suppresses the openedx_tagging "
                "side-effect. Use when the consumer doesn't follow the v2-"
                "Library UsageKey convention or has no openedx_tagging."
            ),
        )

    def handle(self, *args, **options):
        zip_path: str = options["zip_path"]
        library_key: str | None = options.get("library_key")
        publish: bool = options.get("publish", True)
        apply_tags: bool = options.get("apply_tags", True)

        if not os.path.isfile(zip_path):
            raise CommandError(f"No such file: {zip_path}")

        try:
            result = import_learning_package(
                zip_path=zip_path,
                override_lp_key=library_key,
                publish=publish,
                apply_tags=apply_tags,
            )
        except ImportFormatError as exc:
            raise CommandError(f"Bad archive: {exc}") from exc
        except TomlParseError as exc:
            raise CommandError(f"Bad TOML in archive: {exc}") from exc

        self.stdout.write(self.style.SUCCESS(
            f"Imported {result.learning_package_key} (LP id={result.learning_package_id})"
        ))
        self.stdout.write(f"  components created    : {result.num_components_created}")
        self.stdout.write(f"  components updated    : {result.num_components_updated}")
        self.stdout.write(f"  versions written      : {result.num_versions_written}")
        self.stdout.write(f"  static files          : {result.num_static_files}")
        self.stdout.write(f"  collections created   : {result.num_collections_created}")
        self.stdout.write(f"  collections updated   : {result.num_collections_updated}")
        self.stdout.write(f"  tags applied          : {result.num_tags_applied}")
        self.stdout.write(f"  taxonomies created    : {result.num_taxonomies_created}")
        if result.tag_apply_warnings:
            self.stdout.write(self.style.WARNING(
                f"  tag apply warnings    : {len(result.tag_apply_warnings)}"
            ))
            for w in result.tag_apply_warnings[:5]:
                self.stdout.write(self.style.WARNING(f"    - {w}"))

        if result.skipped_containers:
            self.stdout.write(self.style.WARNING(
                f"  containers skipped    : {len(result.skipped_containers)} "
                f"(not yet supported — see importer.py docstring)"
            ))
        if result.skipped_entities:
            self.stdout.write(self.style.WARNING(
                f"  entities skipped      : {len(result.skipped_entities)}"
            ))
            for name, reason in result.skipped_entities[:10]:
                self.stdout.write(self.style.WARNING(f"    - {name}: {reason}"))

        if not publish:
            self.stdout.write(self.style.WARNING(
                "Versions landed as drafts. Run ./manage.py shell and call "
                "openedx_learning.api.authoring.publish_all_drafts(lp_id) when ready."
            ))
