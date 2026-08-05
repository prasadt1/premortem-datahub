from __future__ import annotations

import html
from datetime import datetime, timezone

from premortem.forecast import cleared_bind_table, is_cleared_finding
from premortem.models import BreakSeverity, Forecast
from premortem.notify import NotifyTarget, notify_markdown
from premortem.rank import rank_findings


def _safe_inline(text: str, *, limit: int = 120) -> str:
    """Collapse whitespace and strip backticks so snippets cannot break markdown."""
    collapsed = " ".join(text.split())[:limit].replace("`", "")
    return collapsed


def to_markdown(
    forecast: Forecast,
    *,
    use_exec_count: bool,
    baseline_source: str = "measured",
    notify: list[NotifyTarget] | None = None,
) -> str:
    ranked = rank_findings(forecast.findings, use_exec_count=use_exec_count)
    d = forecast.diff
    change = (
        f"{d.column} → rename to {d.new_column}"
        if d.kind == "rename"
        else f"drop {d.column}"
    )
    if baseline_source == "user-supplied":
        baseline = (
            f"Impact Analysis baseline: {forecast.lineage_dependent_count} "
            f"downstream dependents (baseline: user-supplied)"
        )
    else:
        baseline = (
            f"Impact Analysis baseline: {forecast.lineage_dependent_count} "
            f"downstream dependents"
        )
    lines = [
        f"Schema rehearsal: {change}",
        "",
        baseline,
        "",
    ]
    for sev in (BreakSeverity.HARD, BreakSeverity.SOFT, BreakSeverity.UNKNOWN):
        group = [f for f in ranked if f.severity is sev]
        label = {
            BreakSeverity.HARD: "HARD",
            BreakSeverity.SOFT: "SOFT",
            BreakSeverity.UNKNOWN: "UNKNOWN / needs human",
        }[sev]
        lines.append(f"{label} ({len(group)})")
        if not group:
            lines.append("- (none)")
        for f in group:
            extra = ""
            if use_exec_count and f.exec_count is not None:
                extra = f"  (exec×{f.exec_count})"
            snip = _safe_inline(f.sql_snippet)
            reason = (
                f" — {_safe_inline(f.unknown_reason, limit=200)}"
                if f.unknown_reason
                else ""
            )
            note = (
                f" — agent: {_safe_inline(f.agent_note, limit=200)}"
                if f.agent_note
                else ""
            )
            lines.append(
                f"- {f.query_id} — [{f.evidence}] `{snip}`{extra}{reason}{note}"
            )
        lines.append("")

    cleared = [
        f
        for f in ranked
        if f.severity is BreakSeverity.UNAFFECTED and is_cleared_finding(f.evidence)
    ]
    lines.append(
        "CLEARED (references a same-named column that binds elsewhere) "
        f"({len(cleared)})"
    )
    if not cleared:
        lines.append("- (none)")
    for f in cleared:
        bound = cleared_bind_table(f.evidence) or "?"
        extra = ""
        if use_exec_count and f.exec_count is not None:
            extra = f"  (exec×{f.exec_count})"
        snip = _safe_inline(f.sql_snippet)
        lines.append(
            f"- {f.query_id} — binds to `{bound}` — `{snip}`{extra}"
        )
    lines.append("")

    if notify is not None:
        lines.append("Notify (who to warn before Friday)")
        lines.append(notify_markdown(notify).rstrip())
        lines.append("")

    lines.append(
        f"No query evidence of `{d.column}` on subject: "
        f"{forecast.unaffected_lineage_count}"
    )
    return "\n".join(lines).rstrip() + "\n"


def to_json(forecast: Forecast, *, use_exec_count: bool) -> str:
    ranked = rank_findings(forecast.findings, use_exec_count=use_exec_count)
    payload = forecast.model_copy(update={"findings": ranked})
    return payload.model_dump_json(indent=2)


def _severity_css(sev: BreakSeverity) -> str:
    return {
        BreakSeverity.HARD: "hard",
        BreakSeverity.SOFT: "soft",
        BreakSeverity.UNKNOWN: "unknown",
        BreakSeverity.UNAFFECTED: "cleared",
    }.get(sev, "unknown")


def to_html(
    forecast: Forecast,
    *,
    use_exec_count: bool,
    baseline_source: str = "measured",
    notify: list[NotifyTarget] | None = None,
    generated_at: datetime | None = None,
) -> str:
    """Self-contained shareable report — same content as ``to_markdown``, styled for PR/Slack links."""
    ranked = rank_findings(forecast.findings, use_exec_count=use_exec_count)
    d = forecast.diff
    change = (
        f"{html.escape(d.column)} → rename to {html.escape(d.new_column or '')}"
        if d.kind == "rename"
        else f"drop {html.escape(d.column)}"
    )
    if baseline_source == "user-supplied":
        baseline = (
            f"Impact Analysis baseline: {forecast.lineage_dependent_count} "
            "downstream dependents (user-supplied)"
        )
    else:
        baseline = (
            f"Impact Analysis baseline: {forecast.lineage_dependent_count} "
            "downstream dependents"
        )

    cleared = [
        f
        for f in ranked
        if f.severity is BreakSeverity.UNAFFECTED and is_cleared_finding(f.evidence)
    ]
    counts = {
        BreakSeverity.HARD: sum(1 for f in ranked if f.severity is BreakSeverity.HARD),
        BreakSeverity.SOFT: sum(1 for f in ranked if f.severity is BreakSeverity.SOFT),
        BreakSeverity.UNKNOWN: sum(
            1 for f in ranked if f.severity is BreakSeverity.UNKNOWN
        ),
        "cleared": len(cleared),
    }

    ts = (generated_at or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M UTC")
    urn = html.escape(d.dataset_urn)

    def _finding_rows(group: list[BreakFinding], *, cleared_rows: bool = False) -> str:
        if not group:
            return '<p class="empty">(none)</p>'
        parts: list[str] = []
        for f in group:
            extra = ""
            if use_exec_count and f.exec_count is not None:
                extra = f' <span class="meta">exec×{f.exec_count}</span>'
            reason = ""
            if f.unknown_reason:
                reason = (
                    f'<p class="reason">{html.escape(_safe_inline(f.unknown_reason, limit=240))}</p>'
                )
            note = ""
            if f.agent_note:
                note = (
                    f'<p class="reason">agent: {html.escape(_safe_inline(f.agent_note, limit=240))}</p>'
                )
            bind = ""
            if cleared_rows:
                bound = cleared_bind_table(f.evidence) or "?"
                bind = f' <span class="meta">binds to {html.escape(bound)}</span>'
            parts.append(
                f'<article class="finding">'
                f'<header><code>{html.escape(f.query_id)}</code>'
                f' <span class="chip {_severity_css(f.severity if not cleared_rows else BreakSeverity.UNAFFECTED)}">'
                f'{html.escape(f.evidence)}</span>{extra}{bind}</header>'
                f'<pre class="sql"><code>{html.escape(_safe_inline(f.sql_snippet, limit=500))}</code></pre>'
                f"{reason}{note}</article>"
            )
        return "\n".join(parts)

    notify_block = ""
    if notify is not None:
        notify_block = (
            f'<section><h2>Notify</h2>'
            f'<pre class="notify">{html.escape(notify_markdown(notify).rstrip())}</pre></section>'
        )

    sections = ""
    for sev, title in (
        (BreakSeverity.HARD, "HARD — breaks on deploy"),
        (BreakSeverity.SOFT, "SOFT — select-list rename"),
        (BreakSeverity.UNKNOWN, "UNKNOWN — needs a human"),
    ):
        group = [f for f in ranked if f.severity is sev]
        sections += (
            f'<section><h2>{html.escape(title)} ({len(group)})</h2>'
            f"{_finding_rows(group)}</section>"
        )
    sections += (
        f'<section><h2>CLEARED — false alarm ({len(cleared)})</h2>'
        f"{_finding_rows(cleared, cleared_rows=True)}</section>"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Premortem rehearsal report</title>
  <meta name="description" content="Schema-change rehearsal forecast — shareable snapshot." />
  <style>
    :root {{
      --bg: #fcfcfb;
      --surface: #ffffff;
      --ink: #1a1916;
      --muted: #5c584f;
      --line: #e8e4dc;
      --accent: #eb6834;
      --hard: #7a2e22;
      --hard-bg: #f3e0dc;
      --soft: #5c4a12;
      --soft-bg: #f5eed4;
      --unknown: #1f4d3a;
      --unknown-bg: #e4ebe3;
      --cleared: #3d4a5c;
      --cleared-bg: #e8edf3;
      --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      --sans: system-ui, -apple-system, "Segoe UI", sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: var(--sans);
      color: var(--ink);
      background: var(--bg);
      line-height: 1.5;
    }}
    main {{
      max-width: 52rem;
      margin: 0 auto;
      padding: 1.75rem 1.1rem 3rem;
    }}
    h1 {{
      font-size: clamp(1.4rem, 4vw, 1.85rem);
      margin: 0 0 0.35rem;
      letter-spacing: -0.02em;
    }}
    .lede {{ color: var(--muted); margin: 0 0 1.25rem; max-width: 42rem; }}
    .meta-bar {{
      font-size: 0.85rem;
      color: var(--muted);
      border-top: 1px solid var(--line);
      padding-top: 0.75rem;
      margin-bottom: 1.25rem;
      word-break: break-all;
    }}
    .counts {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(7rem, 1fr));
      gap: 0.65rem;
      margin: 0 0 1.5rem;
    }}
    .count {{
      border: 1px solid var(--line);
      border-radius: 0.5rem;
      padding: 0.65rem 0.75rem;
      background: var(--surface);
    }}
    .count strong {{ display: block; font-size: 1.35rem; }}
    .count.hard strong {{ color: var(--hard); }}
    .count.soft strong {{ color: var(--soft); }}
    .count.unknown strong {{ color: var(--unknown); }}
    .count.cleared strong {{ color: var(--cleared); }}
    section {{ margin: 0 0 1.35rem; }}
    h2 {{
      font-size: 1rem;
      margin: 0 0 0.65rem;
      padding-bottom: 0.35rem;
      border-bottom: 1px solid var(--line);
    }}
    .finding {{
      border: 1px solid var(--line);
      border-radius: 0.45rem;
      background: var(--surface);
      margin: 0 0 0.55rem;
      overflow: hidden;
    }}
    .finding header {{
      padding: 0.45rem 0.65rem;
      font-size: 0.88rem;
      border-bottom: 1px solid var(--line);
      background: #faf9f7;
    }}
    .chip {{
      display: inline-block;
      font-size: 0.72rem;
      font-weight: 600;
      padding: 0.1rem 0.4rem;
      border-radius: 0.25rem;
      margin-left: 0.25rem;
      vertical-align: middle;
    }}
    .chip.hard {{ background: var(--hard-bg); color: var(--hard); }}
    .chip.soft {{ background: var(--soft-bg); color: var(--soft); }}
    .chip.unknown {{ background: var(--unknown-bg); color: var(--unknown); }}
    .chip.cleared {{ background: var(--cleared-bg); color: var(--cleared); }}
    .sql, .notify {{
      margin: 0;
      padding: 0.55rem 0.65rem;
      font-family: var(--mono);
      font-size: 0.78rem;
      white-space: pre-wrap;
      word-break: break-word;
      overflow-x: auto;
    }}
    .reason {{
      margin: 0;
      padding: 0 0.65rem 0.55rem;
      font-size: 0.82rem;
      color: var(--muted);
    }}
    .empty {{ color: var(--muted); font-size: 0.9rem; }}
    footer {{
      margin-top: 1.5rem;
      padding-top: 0.75rem;
      border-top: 1px solid var(--line);
      font-size: 0.82rem;
      color: var(--muted);
    }}
  </style>
</head>
<body>
  <main>
    <p class="lede"><strong>Premortem</strong> — schema-change rehearsal report</p>
    <h1>Schema rehearsal: {change}</h1>
    <p class="lede">{html.escape(baseline)}</p>
    <div class="meta-bar">Dataset: <code>{urn}</code> · Generated {html.escape(ts)}</div>
    <div class="counts">
      <div class="count hard"><strong>{counts[BreakSeverity.HARD]}</strong>HARD</div>
      <div class="count soft"><strong>{counts[BreakSeverity.SOFT]}</strong>SOFT</div>
      <div class="count unknown"><strong>{counts[BreakSeverity.UNKNOWN]}</strong>UNKNOWN</div>
      <div class="count cleared"><strong>{counts["cleared"]}</strong>CLEARED</div>
    </div>
    {sections}
    {notify_block}
    <footer>
      Catalog write-back (tag + Quality assertion) is canonical for engineers in DataHub;
      this page is a shareable snapshot for reviewers.
      No query evidence of <code>{html.escape(d.column)}</code> on subject:
      {forecast.unaffected_lineage_count}.
    </footer>
  </main>
</body>
</html>
"""
