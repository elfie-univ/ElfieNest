"""Minimal, local-only hardware facts used by the optional Ollama recommendation."""

from __future__ import annotations

import os


def get_available_memory_gb() -> int:
    """Return a conservative whole-GiB physical-memory estimate or zero if unknown."""
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
    except (AttributeError, OSError, ValueError):
        return 0
    if not isinstance(pages, int) or not isinstance(page_size, int):
        return 0
    return max(0, pages * page_size // (1024**3))
