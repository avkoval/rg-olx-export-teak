# Why this package exists

## The problem

Open edX's content backbone is being modernised: the `openedx-learning`
package was renamed to `openedx-core` (PyPI 0.45+), with new apps
(`openedx_content`, `openedx_catalog`, `openedx_tagging` flat layout,
`openedx_django_lib`) and a `backup_restore` subpackage that knows how
to emit and ingest OLX archives via `LearningPackageZipper` /
`LearningPackageUnzipper`.

Edx-platform itself has not yet integrated `openedx-core`. As of the
**teak** (Tutor 20.x) and **ulmo** (Tutor 21.x) named releases,
edx-platform still pins `openedx-learning==0.26.x`–`0.30.x` and
imports `openedx_learning.api.*` at ~48 sites across ~32 files. There
is no v2-Library export entry point in stock edx-platform — no
management command, no REST endpoint, no Studio UI button, and the
older `openedx-learning` does not ship the zipper at all.

Replacing `openedx-learning` with `openedx-core` inside such a Tutor
stack is not viable: the runtime imports collide, the deep-vs-flat
layout of `openedx_tagging` collides on `sys.path`, and the schema
renames (`LearningPackage.key` → `package_ref`,
`PublishableEntity.key` → `entity_ref`, etc.) break edx-platform's own
ORM queries.

## What this package does

`rg-olx-export-teak` is a small Django app pip-installed into a Tutor
LMS/CMS image (typically via a Tutor plugin). It walks the
`openedx-learning` 0.26-era ORM directly and writes a zip in the
openedx-core OLX archive format described in
[`docs/FORMAT.md`](FORMAT.md). The zip is byte-compatible with
`LearningPackageUnzipper` from openedx-core 0.45+, so any consumer that
uses that unzipper (in a separate Django process where openedx-core IS
installed cleanly) can ingest what Studio authored.

The package adds a `./manage.py export_lp <lp-key> <output-path>`
command. It does NOT modify Studio, the course-authoring MFE, or any
edx-platform internals; it only reads.

For tagged `<problem>` components, the export injects `<meta>` blocks
into `block.xml` populated from `openedx_tagging.core.tagging.models.ObjectTag`
rows, so taxonomy classifications travel inside the OLX (rather than
relying on a sidecar manifest).

## Why a new package, not a fork or a feature flag

- **Fork of edx-platform.** Far too large a surface to maintain. The
  rename collisions would require rewriting every `openedx_learning.*`
  import site.
- **Feature flag in edx-platform.** Not our codebase to feature-flag.
- **Sidecar Django process running openedx-core.** Possible (the
  alternative considered during planning), but then the sidecar would
  still need to load the LP from the Tutor instance — and since
  openedx-learning 0.26 has no internal export, the sidecar would need
  to walk the 0.26 ORM remotely or replicate the data via ETL. Same
  fundamental work as this package, with extra moving parts (a separate
  Django process, an ETL transport, schema mapping at the boundary).

A small in-Tutor exporter is the path of least operational complexity.

## Lifecycle

This package is bridge code with a known sunset path:

| Era | Producer | Relationship to this package |
|---|---|---|
| now → ~12 mo | `rg-olx-export-teak` (this) | active; only producer for teak/ulmo Studio |
| edx-platform integrates openedx-core | openedx-core's own `LearningPackageZipper` plus a small subclass that injects `<meta>` (already prototyped upstream-side) | this package is decommissioned |
| upstream merges native `<meta>` emission | stock `openedx-core` | the subclass is decommissioned too |

Decommissioning is a Tutor-plugin disable — no data migration is
involved on the producer side; the consumer keeps reading the same zip
format throughout.

## Format authority

The OLX archive layout produced by this package is single-sourced from
upstream openedx-core's fixture; we don't invent a new format. See
[`docs/FORMAT.md`](FORMAT.md) for the bytes-level spec. Any divergence
from openedx-core's output is a bug in this package; bug reports
welcome.
