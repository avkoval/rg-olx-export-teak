# rg-olx-export-teak

OLX zip **exporter and importer** for v2 Libraries on **Open edX teak / ulmo**
(`openedx-learning==0.26.x` through `0.30.x`).

A small Django app pip-installed into a Tutor LMS/CMS image. Two ways
to export (Studio admin or shell), one way to import (shell).

## Use

### Export from the Studio admin

For non-developers — no shell needed:

1. Open Studio admin (assumes Tutor `studio.local.openedx.io:8001` here;
   substitute your CMS host):

   ```
   http://studio.local.openedx.io:8001/admin/oel_publishing/learningpackage/
   ```

   The same page also exists on the LMS admin (`local.openedx.io:8000/admin/...`)
   if your authoring user only has LMS-staff rights.

2. Tick exactly one LearningPackage row (libraries appear here as their
   underlying LP — name matches what Studio shows under *Content → Libraries*).

3. From the **Action** dropdown choose **"Export as OLX zip
   (rg-olx-export-teak)"**, click *Go*.

4. The browser downloads a zip whose filename is derived from the LP key
   (e.g. `lib_KSK_test-export.zip`). Two custom HTTP response headers
   report export stats: `X-RG-OLX-Components` and `X-RG-OLX-Problems-With-Meta`.

Requires `is_staff=True` on the user account. There is currently *no*
admin action for import — use the management command below.

### Export from the management command

For automation, scripted round-trips, or when you want the zip on the
container filesystem rather than downloaded to your laptop:

```sh
tutor dev exec cms ./manage.py cms export_lp \
    <learning-package-key> <output-zip-path-inside-container> \
    [--user <username>] \
    [--origin-server <hostname>] \
    [--allow-invalid]
```

`--allow-invalid` skips `<problem>` components that fail producer-side
validation (no `*response` child, malformed XML) instead of refusing the
whole export.

### Import from the management command

Round-trip testing, restoring backups, and ingesting bundles produced by
openedx-core 0.45+'s `LearningPackageZipper`:

```sh
tutor dev exec cms ./manage.py cms import_lp \
    <zip-path-inside-container> \
    [--library-key <override-key>] \
    [--no-publish]
```

Idempotent: re-running the same zip is safe — same LP key reuses the
LP row, same component `local_key` reuses the component, new versions
are appended only when content differs. After import, run
`./manage.py cms reindex_studio --experimental --incremental` so
Meilisearch picks up the new content and the v2 Library tagging UI works.

See the docstring of `importer.py` for the full behaviour and v0
limitations (containers and tag re-creation are deferred).

### Round-trip in one shot

To prove a zip travels intact through this package, on a fresh LP:

```sh
tutor dev exec cms ./manage.py cms export_lp lib:Demo:roundtrip /tmp/a.zip
tutor dev exec cms ./manage.py cms import_lp /tmp/a.zip --library-key lib:Demo:roundtrip-copy
tutor dev exec cms ./manage.py cms export_lp lib:Demo:roundtrip-copy /tmp/b.zip
diff <(unzip -l /tmp/a.zip | sort) <(unzip -l /tmp/b.zip | sort)
```

Identical file lists indicates a stable round-trip; payload checksums
should match too on stable input. (Tag re-creation is the known gap —
see limitation note above.)

## Format

The export zip is byte-compatible with `openedx_content.applets.backup_restore.zipper.LearningPackageUnzipper`
from upstream **openedx-core 0.45+**, so any importer/consumer running
openedx-core can ingest what Studio authored. For tagged `<problem>`
components, taxonomy classifications travel inside `block.xml` as
`<meta><tag taxonomy="X">VALUE</tag></meta>` blocks (populated from
`openedx_tagging.core.tagging.models.ObjectTag`). The import side
strips these blocks before storage so Studio renders the question
cleanly; recreating the matching `ObjectTag` rows is left to a
follow-up release.

## Why this exists

Stock teak/ulmo has no v2 Library export at all — no management
command, no REST endpoint, no Studio UI button. openedx-core 0.45+
(which has `LearningPackageZipper`) cannot be installed into a teak
Tutor stack: edx-platform itself imports `openedx_learning.api.*` at
~48 sites, and the rename / namespace collisions break the runtime.

This package is the bridge — it walks 0.26's ORM directly and writes
the openedx-core-shaped archive. See [`docs/RATIONALE.md`](docs/RATIONALE.md)
for the full design rationale and lifecycle.

## Format reference

See [`docs/FORMAT.md`](docs/FORMAT.md) for the zip layout spec. In short:

```
package.toml
entities/
  <slug>.toml                                # containers
  xblock.v1/<type>/<slug>.toml               # components
  xblock.v1/<type>/<slug>/component_versions/v<N>/block.xml
  xblock.v1/<type>/<slug>/component_versions/v<N>/static/<asset>
collections/<slug>.toml
```

## Install

A copy-paste-ready Tutor plugin ships with this repo at
[`contrib/tutor-plugin/lp_export.py`](contrib/tutor-plugin/lp_export.py).
Drop it into your `$TUTOR_PLUGINS_ROOT/` directory:

```sh
cp contrib/tutor-plugin/lp_export.py "$TUTOR_PLUGINS_ROOT/"
tutor plugins enable lp_export
tutor config save
tutor images build openedx-dev
tutor dev start --detach lms cms
tutor dev exec cms ./manage.py cms help export_lp
tutor dev exec cms ./manage.py cms help import_lp
```

The plugin pip-installs this package from
`git+https://github.com/avkoval/rg-olx-export-teak.git@main` into the openedx
image's Python environment and adds `rg_olx_export_teak` to both LMS and CMS
`INSTALLED_APPS`. Both `export_lp` and `import_lp` management commands become
available in the LMS and CMS containers. Pin a specific tag (e.g.
`@v0.4.0`) by editing the `RG_OLX_EXPORT_TEAK_GIT_REF` constant in the plugin
file before enabling.

## Develop

```sh
python -m venv .venv
.venv/bin/pip install -e ".[test]"
.venv/bin/pytest tests/
```

77 unit tests cover the pure-Python paths: TOML emit/parse round-trip,
`<meta>` XML injection, slug allocator, tag-row grouping, OLX problem
validation. The Django ORM walker (export) and the openedx-learning
authoring writer (import) are integration-tested only inside a real
Tutor LMS/CMS container — they import `openedx_learning.apps.authoring.*`
model classes that are only available there.

## Compatibility

| Component | Required version |
|---|---|
| Open edX | teak (Tutor 20.x) / ulmo (Tutor 21.x) |
| `openedx-learning` | 0.26.x – 0.30.x |
| `openedx-tagging` (deep path: `openedx_tagging.core.tagging.*`) | shipped with edx-platform release/teak and release/ulmo |
| Python | 3.11 (Tutor's bundled interpreter) — also tested on 3.12 |
| Django | 4.2 (whatever edx-platform pins) |

## Lifecycle

Bridge package — decommission once edx-platform integrates openedx-core
(a future named release). At that point the openedx-core-side plugin
takes over; see [`docs/RATIONALE.md`](docs/RATIONALE.md) §
"Lifecycle".

## Licence

AGPL-3.0-or-later.
