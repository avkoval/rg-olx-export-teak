# rg-olx-export-teak

v2 Library OLX exporter for Open edX **teak** (openedx-learning 0.26 era).

## What this does

Walks a v2 `LearningPackage` in an Open edX Tutor instance running the **teak** named release (or any deployment that pins `openedx-learning==0.26.x`) and emits a zip in the [ADR-0006 §D1](../Sud-ispyt/ok-Sud-Ispyt-shared/adr/0006-olx-bundle-import-format-and-reimport-strategy.md) layout. The zip is consumed by KSK-KI's `bundle_import.py` (which delegates to `openedx_content.applets.backup_restore.zipper.LearningPackageUnzipper` from openedx-core 0.45+).

`<problem>` blocks get a `<meta><tag taxonomy="X">VALUE</tag></meta>` block injected ahead of their response element, populated from `openedx_tagging.core.tagging.models.ObjectTag` rows attached to the `PublishableEntity`.

## Why this exists

Stock Open edX teak has no v2 Library export at all. openedx-core 0.45 (which has the `LearningPackageZipper`) cannot be installed into a teak Tutor stack because edx-platform itself imports `openedx_learning.api.*` at 48 sites — see `~/dev/rg/ki/edx-as-cms/architecture-flow1-flow2.org` for the full compatibility analysis.

This package is the **bridge** until edx-platform integrates openedx-core in a future named release. At that point this package becomes legacy and is replaced by the `feat/meta-tag-export` plugin in [openedx-core](https://github.com/avkoval/openedx-core).

## Status

Early scaffold. See `~/dev/rg/ki/edx-as-cms/architecture-flow1-flow2.org` § "Final recommendation after both spikes" for the implementation plan and milestones.

## Install

This package is intended to be pip-installed into a Tutor `openedx` image via `OPENEDX_EXTRA_PIP_REQUIREMENTS` in a Tutor plugin. See `tutor-plugins/` in the consuming `edx-as-cms` repo (sibling) for the wiring.

## Develop

```bash
python -m venv .venv
.venv/bin/pip install -e ".[test]"
.venv/bin/pytest tests/
```
