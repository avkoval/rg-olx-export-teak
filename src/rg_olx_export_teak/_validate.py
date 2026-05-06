"""OLX validation — pure functions, no Django.

Producer-side defence layer: catch malformed problem OLX *before* a zip
leaves the Tutor process, so consumer-side validators (which exist but
fire later in the pipeline — at import or at exam render) never have
to apologise for our output.

The minimal correctness rule for an exam ``<problem>``: it must have
at least one direct-child element whose tag ends with ``response``
(e.g. ``multiplechoiceresponse``, ``stringresponse``,
``numericalresponse``, ``choiceresponse``, ``optionresponse``,
``customresponse``, ``imageresponse``, etc.). A ``<problem>`` without
any response element is not renderable as a question — it crashes the
exam UI.

We do NOT enforce a *specific* response type here. That's a
consumer-policy decision (e.g. KSK-KI's exam renderer may only support
single-select); this validator is the producer-side floor.
"""
from __future__ import annotations

from lxml import etree


def validate_problem_olx(olx_xml: str | bytes) -> str | None:
    """Return ``None`` if the OLX is renderable, else a short failure reason.

    Validates only when the root is ``<problem>``; non-problem blocks
    (html, video, etc.) pass through (return ``None``).

    Failure modes:

    - Cannot be parsed as XML.
    - Root is ``<problem>`` but has no direct child whose local-name
      ends with ``response``.
    """
    if isinstance(olx_xml, str):
        olx_bytes = olx_xml.encode("utf-8")
    else:
        olx_bytes = olx_xml

    try:
        root = etree.fromstring(olx_bytes)
    except etree.XMLSyntaxError as exc:
        return f"invalid XML: {exc}"

    if root.tag != "problem":
        return None

    for child in root:
        if not isinstance(child.tag, str):  # comments, processing instructions
            continue
        # Ignore namespace prefix if any — match on local-name suffix.
        local = child.tag.rsplit("}", 1)[-1]
        if local.endswith("response"):
            return None

    return "<problem> has no *response child element"
