"""Tutor plugin: install and register ``rg-olx-export-teak`` into LMS+CMS.

Provides the ``./manage.py export_lp`` Django management command in both
the LMS and CMS containers, plus the underlying ``rg_olx_export_teak``
Django app on ``INSTALLED_APPS`` so its ``apps.py`` runs at startup.

Lifecycle: bridge package for the openedx-learning 0.26 era. Decommission
when edx-platform integrates openedx-core (a future named release after
ulmo); at that point switch to the openedx-core ``feat/meta-tag-export``
plugin.

Plan reference: ``architecture-flow1-flow2.org`` § "Path B (revised)".
"""

from tutor import hooks

# Distribution: pip install from a git ref. When iterating locally, swap
# this for a path-mounted editable install via `tutor mounts add <path>` —
# faster turnaround than rebuilding the openedx image on every change.
RG_OLX_EXPORT_TEAK_GIT_URL = "https://github.com/avkoval/rg-olx-export-teak.git"
RG_OLX_EXPORT_TEAK_GIT_REF = "main"

DOCKERFILE_PATCH = f"""
RUN pip install "git+{RG_OLX_EXPORT_TEAK_GIT_URL}@{RG_OLX_EXPORT_TEAK_GIT_REF}#egg=rg-olx-export-teak"
"""

# The Django app must be in INSTALLED_APPS for management commands to be
# discoverable by manage.py. Both LMS and CMS contexts need it: in dev
# we'd typically only run the command from CMS, but stock teak's
# ./manage.py runs against either, and Studio admins are more likely to
# discover the LMS shell by accident.
INSTALLED_APP_PATCH = '''
if "rg_olx_export_teak" not in INSTALLED_APPS:
    INSTALLED_APPS.append("rg_olx_export_teak")
'''

hooks.Filters.ENV_PATCHES.add_items([
    ("openedx-dockerfile-post-python-requirements", DOCKERFILE_PATCH),
    ("openedx-lms-common-settings", INSTALLED_APP_PATCH),
    ("openedx-cms-common-settings", INSTALLED_APP_PATCH),
])
