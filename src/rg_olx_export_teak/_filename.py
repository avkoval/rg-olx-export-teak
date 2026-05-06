"""Filename allocator for entity TOMLs and component folders.

Mirrors the canonical openedx-core 0.45 zipper's collision-avoidance
strategy: slugify the source key, and on slug collision append a short
hash of the original key. This produces names like ``section1-8ca126``
that match upstream fixture conventions.

Pure module — no Django, no DB.
"""
from __future__ import annotations

import hashlib

from django.utils.text import slugify


_HASH_LEN = 6


class FilenameAllocator:
    """Per-archive filename allocator with collision tracking.

    Construct one instance per zip archive and call ``allocate(key)`` for
    every entity / collection. The first call for a given slug returns the
    slug itself; subsequent calls for keys whose slugs collide return the
    hashed variant.

    Slugification uses ``django.utils.text.slugify(..., allow_unicode=True)``
    so Ukrainian / Cyrillic keys survive intact.
    """

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def allocate(self, key: str) -> str:
        """Return a unique-within-this-allocator filename slug for ``key``."""
        slug = _slug(key)
        if slug not in self._seen:
            self._seen.add(slug)
            return slug
        hashed = _hashed_slug(key)
        self._seen.add(hashed)
        return hashed


def _slug(key: str) -> str:
    return slugify(key, allow_unicode=True)


def _hashed_slug(key: str) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:_HASH_LEN]
    return f"{_slug(key)}-{digest}"


def safe_zip_filename(lp_key: str) -> str:
    """Map an LP key (``lib:KSK:test-export``) to a download filename.

    Replaces the colons (browsers/proxies sometimes strip these, Windows
    file systems disallow them) and any path separators with underscores.
    Unicode is preserved — we want the filename recognisable as derived
    from the original key, not slugified.
    """
    safe = lp_key.replace(":", "_").replace("/", "_").replace("\\", "_")
    return f"{safe}.zip"
