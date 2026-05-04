# Archive format produced by `rg-olx-export-teak`

This package emits the same on-disk zip layout that
[openedx-core](https://github.com/openedx/openedx-core) (0.45+) produces
via its `LearningPackageZipper`. The format is portable across producers:
any importer expecting an openedx-core OLX archive — most importantly
openedx-core's own `LearningPackageUnzipper` — will accept what we emit.

This file restates the layout in self-contained form so a downstream
integrator can reason about the expected bytes without chasing upstream
source. The canonical reference fixture lives in
[`openedx-core/tests/openedx_content/applets/backup_restore/fixtures/library_backup/`](https://github.com/openedx/openedx-core/tree/main/tests/openedx_content/applets/backup_restore/fixtures/library_backup).

## Top-level layout

```
package.toml
entities/
  <container-slug>.toml                    # for sections / subsections / units
  <namespace>/                             # e.g. xblock.v1
    <type>/                                # e.g. problem, html, video
      <component-slug>.toml
      <component-slug>/
        component_versions/
          v<N>/
            block.xml
            static/<asset>?                # optional, per-version
collections/
  <collection-slug>.toml
```

Slugs are produced by django's `slugify(..., allow_unicode=True)`. On
collisions inside a single archive, a 6-character hex hash of the source
key is appended (e.g. `section1-8ca126`).

## `package.toml`

One per archive, at the zip root. Two top-level tables:

```toml
[meta]
format_version = 1
created_by = "<username>"                  # optional
created_by_email = "<email>"               # optional
created_at = 2026-05-04T12:00:00Z
origin_server = "<hostname>"               # optional, free-form

[learning_package]
title = "Library test"
key = "lib:WGU:LIB_C001"
description = ""
created = 2025-08-19T04:25:10.988166Z
updated = 2025-08-19T04:25:10.988166Z
```

`[meta]` is emitted before `[learning_package]` for a stable diff order.
The `key` field is a stable opaque identifier of the LearningPackage; on
re-import it is the dedup pivot.

## Entity TOML — components

`entities/<namespace>/<type>/<component-slug>.toml`:

```toml
[entity]
can_stand_alone = true
key = "xblock.v1:problem:abc-123"
created = 2025-09-04T22:37:24.780718Z

[entity.draft]
version_num = 2

[entity.published]
version_num = 2

# ### Versions

[[version]]
title = "Single select"
version_num = 2
```

Rules:

- `[entity.draft]` is omitted entirely if there has never been a draft
  (or it has been reverted).
- `[entity.published]` is always present. If the entity is not currently
  published, the table is empty and a `# unpublished: no published_version_num`
  comment is emitted in its place.
- `[[version]]` is an Array of Tables; one entry per version whose
  payload is bundled into the zip. Typically: draft + published, deduped
  if the same version_num.

## Entity TOML — containers

`entities/<container-slug>.toml`:

```toml
[entity]
can_stand_alone = true
key = "section1"
created = 2025-09-04T22:37:24.780718Z

[entity.draft]
version_num = 1

[entity.published]
version_num = 1

[entity.container.section]                 # one of: section / subsection / unit

# ### Versions

[[version]]
title = "Section 1"
version_num = 1
```

Containers carry no per-version media (their members do); they only need
the entity TOML.

## Component version files

For every `[[version]]` of a Component, payload files are written under
`entities/<namespace>/<type>/<slug>/component_versions/v<N>/`:

- `block.xml` — the OLX text for that version.
- `static/<asset>` — optional, zero or more static assets.

The payload is the verbatim content of the corresponding storage row
(for openedx-learning 0.26 producers: a `Content.text` field, or
`Content.read_file()` if the row stores a file rather than text).

### `<problem>` `<meta>` injection

When the component is `xblock.v1:problem` AND there are taxonomy tags
attached to the entity (looked up by `PublishableEntity.uuid`), the
emitted `block.xml` has a `<meta>` block inserted as the first child of
the `<problem>` root, ahead of the response element:

```xml
<problem display_name="Q1">
  <meta>
    <tag taxonomy="discipline">civil-law</tag>
    <tag taxonomy="section">property-rights</tag>
  </meta>
  <multiplechoiceresponse>
    ...
  </multiplechoiceresponse>
</problem>
```

Rules for the `<meta>` block:

- One `<tag>` per taxonomy / value pair.
- `taxonomy` attribute holds the taxonomy's `export_id` (a stable opaque
  string).
- Values are deduped within a taxonomy; first-seen order preserved.
- Taxonomies are emitted in alphabetical order of `export_id` for
  deterministic diffs.
- Special characters in values are XML-escaped on emit.
- If `<problem>` already has a `<meta>` child, it is **replaced**, not
  duplicated.
- If there are no tags on the entity, no `<meta>` is emitted (no empty
  containers).

## Collection TOML

`collections/<collection-slug>.toml`:

```toml
[collection]
title = "Collection test1"
key = "collection-test"
description = ""
created = 2025-08-19T04:25:27.754968Z
entities = [
    "xblock.v1:html:abc-...",
    "xblock.v1:problem:def-...",
]
```

`entities` is a multi-line array of entity keys (matching `[entity].key`
of the corresponding `entities/.../*.toml` files).

## Re-import semantics expected of the consumer

This producer does not enforce any particular re-import behaviour, but
the openedx-core `LearningPackageUnzipper` (and consumers built on it)
typically:

- Dedup on the SHA-256 of the zip bytes (cheapest gate).
- Match LearningPackages by `[learning_package].key`.
- Match Components by `key` within a LearningPackage.
- Match Collections by `[collection].key`.
- Append a new `ComponentVersion` only when the OLX text differs from
  the existing latest version.
- Replace `<meta>` taxonomy tags wholesale on re-import.

If you build a custom consumer, mirroring those gates is the
straightforward way to make re-imports cheap.
