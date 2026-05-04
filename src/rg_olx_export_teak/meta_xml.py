"""Inject ADR-0006 §D1 ``<meta>`` blocks into ``<problem>`` OLX.

Pure XML transformation, **no database access**. The caller supplies a
``tag_groups`` dict (taxonomy export_id → list of tag values); this module
turns it into the standard ``<meta><tag taxonomy="X">VALUE</tag></meta>``
shape and inserts it as the first child of a ``<problem>`` root.

Why this separation: the same emit logic is needed in two places —

1. `openedx-core` plugin (``feat/meta-tag-export`` branch's
   ``TaggingLearningPackageZipper``) — queries `openedx_tagging.models`
   (flat path).
2. This package's ``rg_olx_export_teak.exporter`` — queries
   `openedx_tagging.core.tagging.models` (deep path used by edx-platform
   release/teak).

The DB query path differs per consumer; the XML output is a single source
of truth. Both consumers call ``inject_meta_block(olx, groups)`` with the
groups they assembled from their respective ORM views.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping

from lxml import etree

log = logging.getLogger(__name__)


def inject_meta_block(
    original_xml: str | bytes,
    tag_groups: Mapping[str, Iterable[str]],
) -> str:
    """Return ``original_xml`` with a ``<meta>`` block inserted into ``<problem>``.

    Returns ``original_xml`` unchanged (as ``str``) when:

    - the root element is not ``<problem>`` (HTML/video/etc. pass-through);
    - ``tag_groups`` is empty (no tags → no empty ``<meta>``);
    - the input fails to parse as XML (a warning is logged).

    If a ``<meta>`` child already exists on the root, it is **replaced**
    (not duplicated). The ``<meta>`` block is always the *first* child of
    ``<problem>``, ahead of the response element.

    Within the ``<meta>`` block:

    - taxonomy ids are emitted in sorted order (deterministic output);
    - within a taxonomy, values are emitted in the iteration order of the
      input ``Iterable`` (caller decides; a list preserves order, a set
      does not);
    - duplicate (taxonomy, value) pairs are dropped; an empty taxonomy
      export_id key is skipped (with a warning).

    Special characters in tag values are escaped per standard XML
    serialisation (``&`` → ``&amp;``, ``<`` → ``&lt;``, etc.).
    """
    if isinstance(original_xml, str):
        original_bytes = original_xml.encode("utf-8")
        original_str = original_xml
    else:
        original_bytes = original_xml
        original_str = original_xml.decode("utf-8")

    try:
        root = etree.fromstring(original_bytes)
    except etree.XMLSyntaxError as exc:
        log.warning("inject_meta_block: could not parse OLX (%s); returning unchanged", exc)
        return original_str

    if root.tag != "problem":
        return original_str

    cleaned: dict[str, list[str]] = {}
    for export_id, values in tag_groups.items():
        if not export_id:
            log.warning("inject_meta_block: skipping empty taxonomy export_id")
            continue
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            ordered.append(value)
        if ordered:
            cleaned[export_id] = ordered

    if not cleaned:
        return original_str

    existing = root.find("meta")
    if existing is not None:
        root.remove(existing)

    meta = etree.Element("meta")
    for export_id in sorted(cleaned):
        for value in cleaned[export_id]:
            tag_el = etree.SubElement(meta, "tag", taxonomy=export_id)
            tag_el.text = value
    root.insert(0, meta)

    return etree.tostring(root, encoding="unicode", pretty_print=True)
