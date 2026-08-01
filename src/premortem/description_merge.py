"""Helpers for non-destructive Premortem sections in dataset descriptions."""

from __future__ import annotations

PREMORTEM_START = "<!-- premortem:forecast -->"
PREMORTEM_END = "<!-- /premortem:forecast -->"


def neutralize_markers(text: str) -> str:
    """Remove delimiter strings that would escape the managed block."""
    return (
        text.replace(PREMORTEM_START, "")
        .replace(PREMORTEM_END, "")
    )


def strip_premortem_section(text: str) -> str:
    """Remove any previous delimited Premortem forecast block.

    Uses ``rfind`` for the end marker so a forged end-marker earlier in the
    block cannot leave attacker text outside the managed region.
    """
    out = text
    while True:
        start = out.find(PREMORTEM_START)
        if start < 0:
            break
        end = out.rfind(PREMORTEM_END)
        if end < 0 or end < start:
            # Malformed prior block — strip from marker to EOF
            out = out[:start].rstrip()
            break
        end += len(PREMORTEM_END)
        out = (out[:start] + out[end:]).strip()
    return out.strip()


def merge_premortem_description(existing: str | None, section_markdown: str) -> str:
    """Keep curated description; replace only the delimited Premortem section."""
    base = strip_premortem_section(existing or "")
    body = neutralize_markers(section_markdown).rstrip()
    block = f"{PREMORTEM_START}\n{body}\n{PREMORTEM_END}"
    if not base:
        return block
    return f"{base.rstrip()}\n\n{block}\n"


def forecast_description_section(*, title: str, body_md: str) -> str:
    """Single builder for the Premortem block written by kit + GraphQL paths."""
    return (
        f"## {title}\n\n{body_md.rstrip()}\n\n"
        "---\n_Premortem schema rehearsal "
        "(hard / soft / unknown / cleared). Tag: premortem_forecast._"
    )
