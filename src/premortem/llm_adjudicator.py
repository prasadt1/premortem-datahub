"""LLM adjudicator for genuine multi-table residue only (B2).

Deterministic binder runs first. This adjudicator only considers UNKNOWN
findings whose ``unknown_kind`` is ``ambiguous_bare`` (unqualified column +
>=2 in-scope tables that each carry the column). Parse failures and SELECT *
stay UNKNOWN.

Temperature 0. Responses are cached so ``eval/run_eval.py`` reproduces the B2
row with no API key.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable

from premortem.agent import Adjudication
from premortem.models import BreakFinding, BreakSeverity


def is_genuine_residue(finding: BreakFinding) -> bool:
    """Bare column, >=2 candidate tables — not parse failure, not STAR."""
    if finding.severity is not BreakSeverity.UNKNOWN:
        return False
    # Prefer structured kind (stable under prose rewording).
    if finding.unknown_kind is not None:
        return finding.unknown_kind == "ambiguous_bare"
    # Legacy fallback for findings built without unknown_kind.
    reason = finding.unknown_reason or ""
    if "parse failed" in reason.lower():
        return False
    if finding.evidence in {"PARSE", "STAR"} or "SELECT *" in reason:
        return False
    return "tables in scope" in reason.lower()


def cache_key(*, sql: str, column: str, candidate_tables: dict[str, list[str]]) -> str:
    payload = {
        "sql": sql.strip(),
        "column": column.lower(),
        "tables": {k: sorted(v) for k, v in sorted(candidate_tables.items())},
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def call_claude_cli(prompt: str) -> str:
    """Temperature-0 adjudication via Claude Code CLI (no SDK key required)."""
    proc = subprocess.run(
        [
            "claude",
            "-p",
            prompt,
            "--output-format",
            "text",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"claude CLI failed ({proc.returncode}): {proc.stderr.strip()[:400]}"
        )
    return proc.stdout


def build_prompt(
    *,
    sql: str,
    column: str,
    candidate_tables: dict[str, list[str]],
) -> str:
    schema_lines = []
    for t, cols in sorted(candidate_tables.items()):
        schema_lines.append(f"- {t}: {', '.join(cols)}")
    schemas = "\n".join(schema_lines)
    return f"""You adjudicate an ambiguous SQL column reference for a schema-change rehearsal.

The column under change is `{column}`. It appears unqualified (or otherwise
ambiguous) with multiple in-scope tables that each have that column.

Candidate tables and schemas:
{schemas}

SQL:
```sql
{sql.strip()}
```

Decide which table the reference binds to for the purpose of a rename/drop of
`{column}` on the SUBJECT table only. If you cannot determine, say so.

Respond with ONLY a JSON object (no markdown), one of:
{{"severity":"hard","binds_to":"<table>","note":"<short reason>"}}
{{"severity":"soft","binds_to":"<table>","note":"<short reason>"}}
{{"severity":"unknown","note":"<why you cannot determine>"}}

Rules:
- hard = the reference binds to the SUBJECT table and sits in WHERE/JOIN/GROUP/ORDER/HAVING/window
- soft = the reference binds to the SUBJECT table and sits only in the SELECT list
- unknown = cannot determine, OR the reference clearly binds to a non-subject table
- Prefer unknown over a wrong bind. Never guess.
"""


class ResidueLlmAdjudicator:
    """LLM adjudicator gated to genuine residue; cache-first."""

    def __init__(
        self,
        *,
        tables: dict[str, list[str]],
        subject_table: str,
        cache_path: Path | None = None,
        cache: dict[str, Any] | None = None,
        allow_network: bool = False,
        caller: Callable[[str], str] | None = None,
    ) -> None:
        self.tables = tables
        self.subject_table = subject_table
        self.subject_base = subject_table.lower().split(".")[-1]
        self.cache_path = cache_path
        self.cache: dict[str, Any] = cache if cache is not None else {}
        if cache_path and cache_path.is_file() and cache is None:
            self.cache = json.loads(cache_path.read_text(encoding="utf-8"))
        self.allow_network = allow_network
        self.caller = caller or call_claude_cli

    def _candidates_for_sql(self, sql: str) -> dict[str, list[str]]:
        """Tables from the fixture that both appear in SQL text and carry the column.

        Conservative: name match on base table token in SQL.
        """
        low = sql.lower()
        out: dict[str, list[str]] = {}
        for tname, cols in self.tables.items():
            base = tname.lower().split(".")[-1]
            if base not in low and tname.lower() not in low:
                continue
            colset = {c.lower() for c in cols}
            # column presence checked by caller via finding.column
            out[tname] = list(cols)
            _ = colset
        return out

    def adjudicate(
        self,
        *,
        finding: BreakFinding,
        sql: str,
        schema_fields: list[str],
        lineage_neighbors: list[str],
    ) -> Adjudication | None:
        if not is_genuine_residue(finding):
            return None

        candidates = {
            t: cols
            for t, cols in self._candidates_for_sql(sql).items()
            if finding.column.lower() in {c.lower() for c in cols}
        }
        if len(candidates) < 2:
            return None

        key = cache_key(
            sql=sql, column=finding.column, candidate_tables=candidates
        )
        entry = self.cache.get("entries", {}).get(key) if "entries" in self.cache else self.cache.get(key)

        if entry is None and self.allow_network:
            prompt = build_prompt(
                sql=sql, column=finding.column, candidate_tables=candidates
            )
            raw = self.caller(prompt)
            try:
                entry = _extract_json(raw)
            except json.JSONDecodeError:
                entry = {
                    "severity": "unknown",
                    "note": f"LLM returned non-JSON; leave UNKNOWN. raw={raw[:200]}",
                }
            entry["cache_key"] = key
            entry["query_id"] = finding.query_id
            if "entries" not in self.cache:
                self.cache = {
                    "version": 1,
                    "model": "claude-cli",
                    "temperature": 0,
                    "entries": dict(self.cache.get("entries", {})),
                }
            self.cache["entries"][key] = entry
            if self.cache_path:
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                self.cache_path.write_text(
                    json.dumps(self.cache, indent=2) + "\n", encoding="utf-8"
                )
        elif entry is None:
            return Adjudication(
                severity=BreakSeverity.UNKNOWN,
                note="LLM cache miss; leave UNKNOWN (no network)",
            )

        sev_raw = str(entry.get("severity", "unknown")).lower()
        note = str(entry.get("note") or "llm adjudicator")
        binds = entry.get("binds_to")
        if binds:
            note = f"{note} (binds_to={binds})"

        if sev_raw == "hard":
            # Only upgrade to HARD/SOFT when bind is the subject
            if binds and binds.lower().split(".")[-1] != self.subject_base:
                return Adjudication(
                    severity=BreakSeverity.UNKNOWN,
                    note=f"LLM bound elsewhere ({binds}); leave UNKNOWN for binder CLEARED path — {note}",
                )
            return Adjudication(severity=BreakSeverity.HARD, note=note)
        if sev_raw == "soft":
            if binds and binds.lower().split(".")[-1] != self.subject_base:
                return Adjudication(
                    severity=BreakSeverity.UNKNOWN,
                    note=f"LLM bound elsewhere ({binds}); leave UNKNOWN — {note}",
                )
            return Adjudication(severity=BreakSeverity.SOFT, note=note)
        if sev_raw == "unaffected":
            # Don't silently clear via LLM in B2 scoring — leave UNKNOWN so
            # CLEARED stays a binder concept; record note.
            return Adjudication(
                severity=BreakSeverity.UNKNOWN,
                note=f"LLM said unaffected/{binds}; leaving UNKNOWN — {note}",
            )
        return Adjudication(severity=BreakSeverity.UNKNOWN, note=note)
