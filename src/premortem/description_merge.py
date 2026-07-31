"""Helpers for non-destructive Premortem sections in dataset descriptions."""

from __future__ import annotations

PREMORTEM_START = "<!-- premortem:forecast -->"
PREMORTEM_END = "<!-- /premortem:forecast -->"


def strip_premortem_section(text: str) -> str:
    """Remove any previous delimited Premortem forecast block."""
    out = text
    while True:
        start = out.find(PREMORTEM_START)
        if start < 0:
            break
        end = out.find(PREMORTEM_END, start)
        if end < 0:
            # Malformed prior block — strip from marker to EOF
            out = out[:start].rstrip()
            break
        end += len(PREMORTEM_END)
        out = (out[:start] + out[end:]).strip()
    return out.strip()


def merge_premortem_description(existing: str | None, section_markdown: str) -> str:
    """Keep curated description; replace only the delimited Premortem section."""
    base = strip_premortem_section(existing or "")
    block = (
        f"{PREMORTEM_START}\n"
        f"{section_markdown.rstrip()}\n"
        f"{PREMORTEM_END}"
    )
    if not base:
        return block
    return f"{base.rstrip()}\n\n{block}\n"
