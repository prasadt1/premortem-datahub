#!/usr/bin/env python3
"""Real-world Premortem run against mozilla/bigquery-etl (not the frozen eval).

Observables only - no gold labels, so no accuracy/precision/recall.

Usage:
  python tools/real_world_mozilla_run.py \\
    --repo /tmp/premortem-rw/bigquery-etl \\
    --out-dir docs
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from premortem.classify import classify_query  # noqa: E402
from premortem.forecast import is_cleared_finding  # noqa: E402
from premortem.models import BreakSeverity  # noqa: E402

SUBJECT_ALIASES = {
    "clients_daily",
    "clients_daily_v6",
    "telemetry.clients_daily",
    "telemetry_derived.clients_daily_v6",
    "moz-fx-data-shared-prod.telemetry.clients_daily",
    "moz-fx-data-shared-prod.telemetry_derived.clients_daily_v6",
}
COLUMN = "client_id"
DIALECT = "bigquery"


def _strip_ansi(s: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", s)


def _strip_jinja(sql: str) -> str:
    sql = re.sub(r"\{\{.*?\}\}", " __JINJA__ ", sql, flags=re.S)
    sql = re.sub(r"\{%.*?%\}", " ", sql, flags=re.S)
    return sql


def _norm_table(name: str) -> str:
    parts = name.lower().replace("`", "").split(".")
    return parts[-1]


def _load_schema_yaml(path: Path) -> list[str]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    fields: list[str] = []
    if isinstance(data, list):
        for row in data:
            if isinstance(row, dict) and row.get("name"):
                fields.append(str(row["name"]))
    elif isinstance(data, dict):
        for row in data.get("fields") or data.get("columns") or []:
            if isinstance(row, dict) and row.get("name"):
                fields.append(str(row["name"]))
    return fields


def collect_schemas(repo: Path) -> dict[str, list[str]]:
    tables: dict[str, list[str]] = {}
    for path in repo.rglob("schema.yaml"):
        # .../dataset/table_name/schema.yaml
        table = path.parent.name.lower()
        fields = _load_schema_yaml(path)
        if fields:
            tables[table] = fields
    return tables


def collect_queries(repo: Path) -> list[dict]:
    out: list[dict] = []
    for path in sorted(repo.rglob("*.sql")):
        if "tests/" in str(path).replace("\\", "/"):
            continue
        if "mozfun" in path.parts:
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        flat = _strip_jinja(raw)
        # Must mention clients_daily somehow
        if not re.search(r"(?i)clients_daily", flat):
            continue
        # And mention client_id (otherwise not in scope for this change)
        if not re.search(r"(?i)\bclient_id\b", flat):
            continue
        rel = str(path.relative_to(repo))
        out.append({"id": rel, "path": rel, "sql": flat, "raw_has_jinja": "{{" in raw or "{%" in raw})
    return out


def unknown_bucket(reason: str | None, evidence: str) -> str:
    r = (reason or "").lower()
    if "parse failed" in r or "sqlglot" in r:
        return "unparseable"
    if "select *" in r or evidence == "SELECT_STAR":
        return "star"
    if "ambiguous" in r or "2 tables" in r or "needs human" in r or "unqualified" in r:
        return "unresolvable"
    if reason:
        return "other_unknown"
    return "other_unknown"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, default=ROOT / "docs")
    ap.add_argument("--sha", default="")
    args = ap.parse_args()
    repo: Path = args.repo
    if not repo.is_dir():
        raise SystemExit(f"repo not found: {repo}")

    sha = args.sha or ""
    if not sha:
        head = repo / ".git" / "HEAD"
        # shallow clone: read via git if possible
        import subprocess

        try:
            sha = subprocess.check_output(
                ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
            ).strip()
        except Exception:
            sha = "unknown"

    schemas = collect_schemas(repo)
    # Ensure subject has client_id
    subject = "clients_daily_v6"
    if subject not in schemas and "clients_daily" in schemas:
        subject = "clients_daily"
    if subject not in schemas:
        # synthesize minimal subject schema from YAML sibling if present
        for cand in ("clients_daily_v6", "clients_daily"):
            p = list(repo.rglob(f"**/{cand}/schema.yaml"))
            if p:
                schemas[cand] = _load_schema_yaml(p[0])
                subject = cand
                break
    if COLUMN.lower() not in {f.lower() for f in schemas.get(subject, [])}:
        schemas.setdefault(subject, [])
        if COLUMN not in schemas[subject]:
            schemas[subject] = list(schemas[subject]) + [COLUMN]

    # Alias subject names to same field list for binder
    subject_fields = schemas[subject]
    for alias in (
        "clients_daily",
        "clients_daily_v6",
        "clients_daily_joined_v1",
    ):
        schemas.setdefault(alias, subject_fields)

    queries = collect_queries(repo)
    findings = []
    verdicts = Counter()
    unknown_reasons = Counter()
    parse_fail_examples = []
    cleared_examples = []
    ugly = []

    tables_resolved = 0
    tables_unresolved_mentions = 0

    for q in queries:
        result = classify_query(
            q["sql"],
            column=COLUMN,
            dialect=DIALECT,
            subject_table=subject,
            tables=schemas,
        )
        sev = result.severity
        # CLEARED is UNAFFECTED + BOUND_ELSEWHERE
        label = sev.value
        if sev is BreakSeverity.UNAFFECTED and is_cleared_finding(result.evidence):
            label = "cleared"
        verdicts[label] += 1

        if sev is BreakSeverity.UNKNOWN:
            bucket = unknown_bucket(result.unknown_reason, result.evidence)
            unknown_reasons[bucket] += 1
            if bucket == "unparseable":
                parse_fail_examples.append(
                    {
                        "id": q["id"],
                        "reason": _strip_ansi(result.unknown_reason or ""),
                        "sql_head": _strip_ansi(q["sql"][:400]),
                    }
                )

        row = {
            "id": q["id"],
            "severity": label,
            "evidence": result.evidence,
            "unknown_reason": result.unknown_reason,
            "snippet": result.snippet[:300],
            "had_jinja": q["raw_has_jinja"],
        }
        findings.append(row)

        if label == "cleared" and len(cleared_examples) < 5:
            cleared_examples.append(row)
        if label == "unknown" and len(ugly) < 8:
            ugly.append(row)

    # Table-resolution: among SQL files, count unique physical tables mentioned
    # that we either had schema for or not (approximate via FROM/JOIN tokens)
    table_pat = re.compile(
        r"(?i)(?:FROM|JOIN)\s+`?([a-zA-Z0-9_\-]+(?:\.[a-zA-Z0-9_\-]+){0,2})`?"
    )
    seen_ok: set[str] = set()
    seen_miss: set[str] = set()
    for q in queries:
        for m in table_pat.finditer(q["sql"]):
            t = _norm_table(m.group(1))
            if t in {"select", "unnest", "x"}:
                continue
            if t in schemas:
                seen_ok.add(t)
            else:
                seen_miss.add(t)
    tables_resolved = len(seen_ok)
    tables_unresolved_mentions = len(seen_miss)

    n = len(queries)
    parse_ok = n - unknown_reasons.get("unparseable", 0)
    # More precise parse: count only those whose unknown_reason is parse failed
    # Actually some parse failures might be the only signal - also statements that
    # classified as hard/soft parsed fine.
    parse_failures = unknown_reasons.get("unparseable", 0)
    parse_rate = (n - parse_failures) / n if n else 0.0

    cmd = (
        f"python tools/real_world_mozilla_run.py --repo {repo} "
        f"--out-dir {args.out_dir} --sha {sha}"
    )

    raw = {
        "project": "mozilla/bigquery-etl",
        "repo_url": "https://github.com/mozilla/bigquery-etl",
        "commit_sha": sha,
        "subject_table": subject,
        "column": COLUMN,
        "dialect": DIALECT,
        "command": cmd,
        "method_note": (
            "Not the frozen eval. No gold labels - observables only. "
            "Queries: *.sql under the repo mentioning clients_daily and client_id; "
            "tests/ and mozfun excluded. Jinja {{ }} / {% %} stripped to placeholders."
        ),
        "query_count": n,
        "parse_rate": round(parse_rate, 4),
        "parse_failures": parse_failures,
        "verdicts": dict(verdicts),
        "unknown_breakdown": dict(unknown_reasons),
        "table_resolution": {
            "schemas_loaded": len(schemas),
            "distinct_tables_with_schema_seen_in_sql": tables_resolved,
            "distinct_tables_without_schema_seen_in_sql": tables_unresolved_mentions,
            "resolution_rate_among_mentioned": (
                round(tables_resolved / (tables_resolved + tables_unresolved_mentions), 4)
                if (tables_resolved + tables_unresolved_mentions)
                else None
            ),
        },
        "findings": findings,
        "parse_fail_examples": parse_fail_examples[:10],
        "cleared_examples": cleared_examples,
        "unknown_examples": ugly,
    }

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "real-world-run-raw.json"
    raw_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")

    # Pick 3-5 concrete examples spanning outcomes
    examples = []
    for label in ("hard", "soft", "cleared", "unknown"):
        hit = next((f for f in findings if f["severity"] == label), None)
        if hit:
            examples.append(hit)
    # ugliest unknown extras
    for f in ugly:
        if f not in examples and len(examples) < 5:
            examples.append(f)

    md = []
    md.append("# Real-world run - mozilla/bigquery-etl")
    md.append("")
    md.append(
        "> **Not the frozen eval.** There are no gold labels on this corpus, so "
        "this report does **not** claim accuracy, precision, or recall. It only "
        "records observables from running the binder-only classifier on foreign "
        "production SQL. Published as returned - not tuned."
    )
    md.append("")
    md.append("| field | value |")
    md.append("|---|---|")
    md.append("| project | [mozilla/bigquery-etl](https://github.com/mozilla/bigquery-etl) |")
    md.append(f"| commit | `{sha}` |")
    md.append(f"| subject table | `{subject}` (aliases: clients_daily / clients_daily_v6) |")
    md.append(f"| column under change | `{COLUMN}` |")
    md.append(f"| dialect | `{DIALECT}` |")
    md.append(f"| queries scored | {n} |")
    md.append("")
    md.append("## Command")
    md.append("")
    md.append("```bash")
    md.append(cmd)
    md.append("```")
    md.append("")
    md.append(f"Raw output: [`docs/real-world-run-raw.json`](real-world-run-raw.json)")
    md.append("")
    md.append("## Parse rate")
    md.append("")
    md.append(
        f"**{parse_rate:.2%}** ({n - parse_failures}/{n}) statements produced a "
        f"non-parse-failure verdict. Parse failures: **{parse_failures}** "
        "(typically heavy Jinja, BigQuery scripting, or sqlglot coverage gaps)."
    )
    md.append("")
    if parse_fail_examples:
        md.append("Example parse failures:")
        md.append("")
        for ex in parse_fail_examples[:3]:
            md.append(f"- `{ex['id']}` - {ex['reason']}")
        md.append("")
    md.append("## Verdict distribution")
    md.append("")
    md.append("| verdict | count | share |")
    md.append("|---|---:|---:|")
    for k in ("hard", "soft", "unknown", "cleared", "unaffected"):
        c = verdicts.get(k, 0)
        if c:
            md.append(f"| {k} | {c} | {c/n:.1%} |")
    md.append("")
    md.append("## UNKNOWN breakdown")
    md.append("")
    md.append("| reason bucket | count |")
    md.append("|---|---:|")
    for k, c in sorted(unknown_reasons.items(), key=lambda kv: -kv[1]):
        md.append(f"| {k} | {c} |")
    md.append("")
    md.append("## Table-resolution rate")
    md.append("")
    tr = raw["table_resolution"]
    md.append(
        f"Loaded **{tr['schemas_loaded']}** table schemas from `schema.yaml`. "
        f"Among distinct tables mentioned in the scored SQL, "
        f"**{tr['distinct_tables_with_schema_seen_in_sql']}** had a schema and "
        f"**{tr['distinct_tables_without_schema_seen_in_sql']}** did not "
        f"(resolution rate "
        f"**{tr['resolution_rate_among_mentioned']}**)."
    )
    md.append("")
    md.append("## Concrete examples")
    md.append("")
    for i, ex in enumerate(examples[:5], 1):
        md.append(f"### {i}. `{ex['id']}` -> **{ex['severity'].upper()}**")
        md.append("")
        md.append(f"- evidence: `{ex['evidence']}`")
        if ex.get("unknown_reason"):
            md.append(f"- unknown_reason: {ex['unknown_reason']}")
        md.append("")
        md.append("```sql")
        md.append((ex.get("snippet") or "")[:500])
        md.append("```")
        md.append("")
    md.append("## Classifier-defect flags (for Aug 3 triage)")
    md.append("")
    md.append(
        "Items below looked surprising on inspection of the raw output - possible "
        "defects rather than honest UNKNOWN. No code was changed in response."
    )
    md.append("")
    # Heuristic flags
    flags = []
    for f in findings:
        if f["severity"] == "unaffected" and re.search(
            r"(?i)clients_daily.*client_id|client_id.*clients_daily", f.get("snippet") or ""
        ):
            flags.append(
                f"possible miss (unaffected but snippet ties client_id to clients_daily): `{f['id']}`"
            )
        if f["severity"] == "hard" and f.get("had_jinja") and " __JINJA__ " in (
            f.get("snippet") or ""
        ):
            flags.append(
                f"HARD after Jinja stripping - verify binding still meaningful: `{f['id']}`"
            )
        if f["severity"] == "cleared":
            ev = f.get("evidence") or ""
            if ev.startswith("BOUND_ELSEWHERE:"):
                for t in ev.split(":", 1)[1].split(","):
                    t = t.strip()
                    if t in {"client_info", "payload", "content", "parent"} or (
                        t.endswith("_v1")
                        and "clients_daily" not in t
                        and "." not in t
                    ):
                        flags.append(
                            f"possible binder defect: CLEARED to non-table `{t}` "
                            f"in `{f['id']}` ({ev})"
                        )
                        break
    # de-dupe while preserving order
    seen: set[str] = set()
    uniq = []
    for fl in flags:
        if fl not in seen:
            seen.add(fl)
            uniq.append(fl)
    flags = uniq
    if not flags:
        md.append(
            "_No automatic defect flags fired beyond the UNKNOWN/parse mass. "
            "Review the UNKNOWN unresolvable bucket and parse failures manually._"
        )
    else:
        for fl in flags[:8]:
            md.append(f"- {fl}")
    md.append("")
    md.append("## Honesty note")
    md.append("")
    md.append(
        "Jinja templating was stripped to placeholders before sqlglot. That "
        "inflates parse failures and can distort binding for models that are "
        "only valid after dbt compilation. A compiled-manifest follow-up would "
        "be stricter; this run deliberately used the public SQL as checked in."
    )
    md.append("")

    md_path = out_dir / "real-world-run.md"
    md_path.write_text("\n".join(md), encoding="utf-8")
    print(f"wrote {md_path}")
    print(f"wrote {raw_path}")
    print(f"queries={n} verdicts={dict(verdicts)} parse_rate={parse_rate:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
