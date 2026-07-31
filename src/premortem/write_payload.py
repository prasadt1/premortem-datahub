"""Build the write_payload handed to the host agent (DataHub MCP applies as-is)."""

from __future__ import annotations

from premortem.catalog.graphql import FORECAST_TAG_ID, FORECAST_TAG_URN
from premortem.description_merge import merge_premortem_description
from premortem.forecast import is_cleared_finding
from premortem.models import BreakSeverity, Forecast

# Stable assertion identity — seeder and write_payload must share this URN.
CAMERA_ASSERTION_URN = "urn:li:assertion:premortem-order-status-rehearsal"
DEFAULT_FORECAST_URL = (
    "https://github.com/prasadt1/premortem-datahub/blob/main/examples/"
    "forecast-order-status.md"
)


def _counts(forecast: Forecast) -> dict[str, int]:
    hard = soft = unknown = cleared = 0
    for f in forecast.findings:
        if f.severity is BreakSeverity.HARD:
            hard += 1
        elif f.severity is BreakSeverity.SOFT:
            soft += 1
        elif f.severity is BreakSeverity.UNKNOWN:
            unknown += 1
        elif f.severity is BreakSeverity.UNAFFECTED and is_cleared_finding(f.evidence):
            cleared += 1
    return {
        "hard": hard,
        "soft": soft,
        "unknown": unknown,
        "cleared": cleared,
        "no_query_evidence": forecast.unaffected_lineage_count,
    }


def assertion_copy(forecast: Forecast) -> dict:
    """Camera-ready assertion fields (dataset-scoped; column in description)."""
    d = forecast.diff
    change = (
        f"rename {d.column} → {d.new_column}"
        if d.kind == "rename" and d.new_column
        else f"drop {d.column}"
    )
    counts = _counts(forecast)
    title = f"Schema rehearsal: {change}"
    description = (
        f"{title}. "
        f"HARD={counts['hard']} SOFT={counts['soft']} "
        f"UNKNOWN={counts['unknown']} CLEARED={counts['cleared']}. "
        f"Impact Analysis baseline: {forecast.lineage_dependent_count} downstream. "
        f"(OSS note: fieldPath omitted — assertionRunEvent rejects schemaField "
        f"asserteeUrn; column `{d.column}` named here instead.)"
    )
    return {
        "urn": CAMERA_ASSERTION_URN,
        "entity_urn": d.dataset_urn,
        "platform": "premortem",
        "type": "Premortem schema rehearsal",
        "title": title,
        "description": description,
        "column": d.column,
        "field_path": None,  # documented OSS limitation
        "external_url": DEFAULT_FORECAST_URL,
        "counts": counts,
        "report_result": "FAILURE",
    }


def build_write_payload(
    forecast: Forecast,
    *,
    markdown: str,
    external_url: str | None = None,
    existing_description: str | None = None,
) -> dict:
    """Payload for the host agent — apply via DataHub MCP mutations as-is.

    Description markdown is merged into any existing curated text: a previous
    ``<!-- premortem:forecast -->`` block is replaced; everything else is kept.
    Host still applies the returned string verbatim (operation=replace of the
    full merged description).
    """
    assertion = assertion_copy(forecast)
    if external_url is not None:
        assertion["external_url"] = external_url
    title = assertion["title"]
    section = f"## {title}\n\n{markdown}"
    merged = merge_premortem_description(existing_description, section)
    return {
        "assertion": assertion,
        "tag": {
            "urn": FORECAST_TAG_URN,
            "id": FORECAST_TAG_ID,
            "name": "Premortem Forecast",
            "ensure_exists": True,
            "entity_urn": forecast.diff.dataset_urn,
        },
        "description": {
            "entity_urn": forecast.diff.dataset_urn,
            "operation": "replace",
            "markdown": merged,
        },
    }
