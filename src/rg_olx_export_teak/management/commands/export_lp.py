"""Django management command: ``./manage.py export_lp <lp-key> <output-path>``.

Invocation inside a Tutor LMS or CMS container::

    tutor dev exec cms ./manage.py cms export_lp \\
        lib:ORG:LIB_KEY /openedx/data/exports/lib_key.zip \\
        --user admin \\
        --origin-server studio.example.org

The ``<lp-key>`` argument is the value stored as ``LearningPackage.key`` in
``openedx-learning`` 0.26 (also written verbatim into the archive's
``package.toml``). ``<output-path>`` is the path **inside** the container.
"""
from __future__ import annotations

from datetime import datetime, timezone

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from openedx_learning.apps.authoring.publishing.models import LearningPackage

from rg_olx_export_teak.exporter import (
    export_learning_package,
    ExportValidationError,
)
from rg_olx_export_teak.records import ExportContext


class Command(BaseCommand):
    help = (
        "Export a v2 LearningPackage from openedx-learning 0.26 as an "
        "OLX zip in the openedx-core 0.45+ archive format (consumable "
        "by openedx-core's LearningPackageUnzipper). See docs/FORMAT.md."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "learning_package_key",
            help="LearningPackage.key value (e.g. 'lib:WGU:LIB_C001').",
        )
        parser.add_argument(
            "output_path",
            help="Destination zip path. Will be overwritten if it exists.",
        )
        parser.add_argument(
            "--user",
            dest="username",
            default=None,
            help=(
                "Username to attribute the export to. Used to populate the "
                "[meta].created_by / created_by_email fields of package.toml."
            ),
        )
        parser.add_argument(
            "--origin-server",
            dest="origin_server",
            default=None,
            help=(
                "Origin-server hint written into package.toml. Free-form "
                "string; useful for tracing where the bundle came from."
            ),
        )
        parser.add_argument(
            "--allow-invalid",
            dest="allow_invalid",
            action="store_true",
            default=False,
            help=(
                "Skip <problem> components that fail producer-side "
                "validation (no *response child, malformed XML) instead "
                "of failing the whole export. Default: strict — refuse "
                "to write the zip if any problem is invalid."
            ),
        )

    def handle(self, *args, **options):
        lp_key: str = options["learning_package_key"]
        output_path: str = options["output_path"]
        username: str | None = options.get("username")
        origin_server: str | None = options.get("origin_server")
        allow_invalid: bool = options.get("allow_invalid", False)

        try:
            lp = LearningPackage.objects.get(key=lp_key)
        except LearningPackage.DoesNotExist as exc:
            raise CommandError(f"No LearningPackage found with key={lp_key!r}") from exc

        created_by, created_by_email = self._resolve_user(username)

        context = ExportContext(
            created_at=datetime.now(tz=timezone.utc),
            created_by=created_by,
            created_by_email=created_by_email,
            origin_server=origin_server,
        )

        try:
            result = export_learning_package(
                learning_package_id=lp.id,
                output_path=output_path,
                context=context,
                allow_invalid=allow_invalid,
            )
        except ExportValidationError as exc:
            self.stderr.write(self.style.ERROR(
                f"Export refused — {len(exc.invalid)} problem(s) failed validation:"
            ))
            for key, reason in exc.invalid:
                self.stderr.write(self.style.ERROR(f"  - {key}: {reason}"))
            self.stderr.write(self.style.WARNING(
                "\nFix the components in Studio (publish a new version with a *response "
                "element), or re-run with --allow-invalid to skip them."
            ))
            raise CommandError(f"{len(exc.invalid)} invalid problem(s); zip not written.") from exc

        self.stdout.write(self.style.SUCCESS(f"Exported {lp_key} -> {result.output_path}"))
        self.stdout.write(f"  components            : {result.num_components}")
        self.stdout.write(f"  problems with <meta>  : {result.num_problems_with_meta}")
        self.stdout.write(f"  static files          : {result.num_static_files}")
        self.stdout.write(f"  containers            : {result.num_containers}")
        self.stdout.write(f"  collections           : {result.num_collections}")
        if result.invalid_problems:
            self.stdout.write(self.style.WARNING(
                f"  invalid problems skipped: {len(result.invalid_problems)}"
            ))
            for key, reason in result.invalid_problems[:10]:
                self.stdout.write(self.style.WARNING(f"    - {key}: {reason}"))
        if result.skipped_entities:
            self.stdout.write(self.style.WARNING(
                f"  skipped (no body)    : {len(result.skipped_entities)} "
                f"({', '.join(result.skipped_entities[:5])}...)"
            ))

    @staticmethod
    def _resolve_user(username: str | None) -> tuple[str | None, str | None]:
        if not username:
            return None, None
        User = get_user_model()
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist as exc:
            raise CommandError(
                f"User {username!r} not found. Pass an existing username or omit --user."
            ) from exc
        return user.username, getattr(user, "email", None) or None
