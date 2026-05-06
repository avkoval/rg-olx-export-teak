"""Django admin: "Export as OLX zip" action on the LearningPackage list page.

Adds a Django admin action that lets a staff user select one
``LearningPackage`` row in ``/admin/`` and get an OLX zip download
without needing a shell. Same export logic as the ``export_lp``
management command, just plumbed through an HTTP response.

Available wherever this app is in ``INSTALLED_APPS`` and the user has
``is_staff=True``. In a Tutor deployment, that's both LMS and CMS
admins (``/admin/...``).

Why re-register the model: ``openedx-learning`` already registers
``LearningPackage`` with its own ``ModelAdmin``. Django's admin only
permits one registration per model, so we ``unregister`` first.
"""
from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime, timezone

from django.contrib import admin, messages
from django.http import HttpResponse

from openedx_learning.apps.authoring.publishing.models import LearningPackage

from ._filename import safe_zip_filename
from .exporter import export_learning_package
from .records import ExportContext

log = logging.getLogger(__name__)


@admin.action(description="Export as OLX zip (rg-olx-export-teak)")
def export_as_olx_zip(modeladmin, request, queryset):
    """Stream one selected LearningPackage as a zip download."""
    if queryset.count() != 1:
        modeladmin.message_user(
            request,
            "Select exactly one LearningPackage to export.",
            level=messages.WARNING,
        )
        return None

    lp = queryset.first()
    user = request.user

    context = ExportContext(
        created_at=datetime.now(tz=timezone.utc),
        created_by=getattr(user, "username", None) or None,
        created_by_email=(getattr(user, "email", None) or None) or None,
        origin_server=request.get_host(),
    )

    # Export to a temp file, then read into the HTTP response. Streaming
    # directly into HttpResponse would require a different shape from
    # exporter.export_learning_package which writes to a path; for v0.2
    # the temp-file round-trip is fine — exam libraries are small (under a
    # few MB).
    fd, zip_path = tempfile.mkstemp(suffix=".zip", prefix=f"lp-{lp.id}-")
    os.close(fd)
    try:
        try:
            result = export_learning_package(lp.id, zip_path, context=context)
        except Exception as exc:  # noqa: BLE001 — surface in admin, log details
            log.exception("Admin export of LP id=%s failed", lp.id)
            modeladmin.message_user(
                request,
                f"Export failed: {type(exc).__name__}: {exc}",
                level=messages.ERROR,
            )
            return None

        with open(zip_path, "rb") as fh:
            zip_bytes = fh.read()
    finally:
        try:
            os.unlink(zip_path)
        except OSError:
            log.warning("Could not unlink temp file %s", zip_path)

    filename = safe_zip_filename(lp.key)
    response = HttpResponse(zip_bytes, content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["X-RG-OLX-Components"] = str(result.num_components)
    response["X-RG-OLX-Problems-With-Meta"] = str(result.num_problems_with_meta)
    return response


# openedx-learning ships its own LearningPackageAdmin — drop it and replace
# with one that adds our action. Other fields stay simple; we don't need
# to mirror upstream's full layout.
try:
    admin.site.unregister(LearningPackage)
except admin.sites.NotRegistered:
    pass


@admin.register(LearningPackage)
class LearningPackageAdmin(admin.ModelAdmin):
    list_display = ("id", "key", "title", "created", "updated")
    list_display_links = ("id", "key")
    search_fields = ("key", "title")
    readonly_fields = ("uuid", "created", "updated")
    ordering = ("-updated",)
    actions = (export_as_olx_zip,)
