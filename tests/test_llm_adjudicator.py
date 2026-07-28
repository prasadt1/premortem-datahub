"""Residue LLM adjudicator — only genuine multi-table UNKNOWNs."""

from __future__ import annotations

from premortem.llm_adjudicator import is_genuine_residue
from premortem.models import BreakFinding, BreakSeverity


def test_is_genuine_residue_multi_table():
    f = BreakFinding(
        query_id="q05",
        sql_snippet="SELECT ...",
        severity=BreakSeverity.UNKNOWN,
        column="order_status",
        evidence="WHERE",
        unknown_reason="unqualified `order_status` with 2 tables in scope; needs human/agent",
    )
    assert is_genuine_residue(f)


def test_parse_and_star_are_not_residue():
    parse = BreakFinding(
        query_id="q09",
        sql_snippet="x",
        severity=BreakSeverity.UNKNOWN,
        column="order_status",
        evidence="PARSE",
        unknown_reason="sqlglot parse failed: boom",
    )
    star = BreakFinding(
        query_id="q04",
        sql_snippet="x",
        severity=BreakSeverity.UNKNOWN,
        column="order_status",
        evidence="STAR",
        unknown_reason="SELECT * may hide column references; needs schema expand or human",
    )
    assert not is_genuine_residue(parse)
    assert not is_genuine_residue(star)
