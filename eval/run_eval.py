"""Frozen-eval harness: score the classifier (and adjudicated pipeline) against gold labels.

What is FROZEN: eval/corpus/*.sql, eval/schema.json, eval/labels.json (pinned by commit +
sha256 recorded in eval/README.md). This harness file is an adapter and may evolve
(e.g., when the multi-table binder lands) — changing it never changes the benchmark;
changing corpus/labels after results exist invalidates the eval.

Runs (reported separately, spec §3.9):
  B0  every-dependent-breaks  — predict `hard` for everything (the Impact-Analysis-only bar)
  B1  substring grep          — `hard` iff the column name appears in the SQL text
  C   classifier              — premortem.classify.classify_query, no adjudication
  C+A classifier + adjudicator— rehearse(..., adjudicate=True) (binder; LLM off by default)

Usage:
  python eval/run_eval.py            # all runs, markdown to stdout
  python eval/run_eval.py --json     # machine-readable results
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

EVAL_DIR = Path(__file__).parent
sys.path.insert(0, str(EVAL_DIR.parent / "src"))

from premortem.agent import rehearse  # noqa: E402
from premortem.classify import classify_query  # noqa: E402
from premortem.models import QueryRecord, SchemaDiff  # noqa: E402

CLASSES = ["hard", "soft", "unknown", "unaffected"]


def load_fixture():
    schema = json.loads((EVAL_DIR / "schema.json").read_text())
    labels = json.loads((EVAL_DIR / "labels.json").read_text())
    cases = []
    for case in labels["cases"]:
        sql = (EVAL_DIR / "corpus" / f"{case['id']}.sql").read_text()
        cases.append({**case, "sql": sql})
    return schema, labels, cases


def predict_b0(cases, **_):
    return {c["id"]: "hard" for c in cases}


def predict_b1(cases, column, **_):
    return {
        c["id"]: ("hard" if column.lower() in c["sql"].lower() else "unaffected")
        for c in cases
    }


def predict_classifier(cases, column, dialect, **_):
    return {
        c["id"]: classify_query(c["sql"], column=column, dialect=dialect).severity.value
        for c in cases
    }


def predict_adjudicated(cases, column, dialect, schema):
    """Classifier + adjudication via the library's rehearse() entry point.

    ADAPTER NOTE: today rehearse() accepts the subject's schema_fields only.
    When the multi-table binder lands, thread the full table->columns fixture
    (schema["tables"]) through here. The metrics below stay unchanged.
    """
    subject = schema["subject"]
    diff = SchemaDiff(
        dataset_urn=f"eval:{subject['dataset']}",
        kind=subject["change"]["kind"],
        column=column,
        new_column=subject["change"].get("new_column"),
    )
    queries = [QueryRecord(query_id=c["id"], sql=c["sql"]) for c in cases]
    subject_fields = schema["tables"][subject["dataset"]]
    forecast = rehearse(
        diff=diff,
        queries=queries,
        dialect=dialect,
        schema_fields=subject_fields,
        adjudicate=True,
    )
    by_id = {f.query_id: f.severity.value for f in forecast.findings}
    return {c["id"]: by_id.get(c["id"], "unaffected") for c in cases}


def score(cases, preds):
    matrix = {g: {p: 0 for p in CLASSES} for g in CLASSES}
    per_stratum = defaultdict(lambda: {"n": 0, "correct": 0, "misses": []})
    for c in cases:
        gold, pred = c["gold"], preds[c["id"]]
        matrix[gold][pred] += 1
        s = per_stratum[c["stratum"]]
        s["n"] += 1
        if gold == pred:
            s["correct"] += 1
        else:
            s["misses"].append(f"{c['id']}:{gold}->{pred}")

    def prec(cls):
        tp = matrix[cls][cls]
        fp = sum(matrix[g][cls] for g in CLASSES if g != cls)
        return tp / (tp + fp) if tp + fp else None

    def rec(cls):
        tp = matrix[cls][cls]
        fn = sum(matrix[cls][p] for p in CLASSES if p != cls)
        return tp / (tp + fn) if tp + fn else None

    decoys = [c for c in cases if c["stratum"] == "decoy"]
    decoy_fp = sum(1 for c in decoys if preds[c["id"]] != "unaffected")
    n = len(cases)
    return {
        "accuracy": sum(matrix[g][g] for g in CLASSES) / n,
        "confusion": matrix,
        "per_class": {c: {"precision": prec(c), "recall": rec(c)} for c in CLASSES},
        "hard_precision": prec("hard"),
        "hard_recall": rec("hard"),
        "unknown_rate": sum(1 for c in cases if preds[c["id"]] == "unknown") / n,
        "decoy_false_positive_rate": decoy_fp / len(decoys) if decoys else None,
        "per_stratum": dict(per_stratum),
    }


def adjudicator_lift(cases, base_preds, adj_preds):
    """How often adjudication binds an UNKNOWN, and how often correctly."""
    changed = [
        c for c in cases
        if base_preds[c["id"]] == "unknown" and adj_preds[c["id"]] != "unknown"
    ]
    unknowns = [c for c in cases if base_preds[c["id"]] == "unknown"]
    correct = sum(1 for c in changed if adj_preds[c["id"]] == c["gold"])
    return {
        "base_unknowns": len(unknowns),
        "bound": len(changed),
        "bind_rate": len(changed) / len(unknowns) if unknowns else None,
        "bind_accuracy": correct / len(changed) if changed else None,
        "bound_cases": [f"{c['id']}:{adj_preds[c['id']]}(gold {c['gold']})" for c in changed],
    }


def fmt(x):
    return "n/a" if x is None else f"{x:.2f}"


def to_markdown(results, lift):
    lines = ["# Eval results", ""]
    lines.append("| run | accuracy | HARD prec | HARD rec | UNKNOWN rate | decoy FP rate |")
    lines.append("|---|---|---|---|---|---|")
    for name, r in results.items():
        lines.append(
            f"| {name} | {fmt(r['accuracy'])} | {fmt(r['hard_precision'])} "
            f"| {fmt(r['hard_recall'])} | {fmt(r['unknown_rate'])} "
            f"| {fmt(r['decoy_false_positive_rate'])} |"
        )
    lines += ["", f"Adjudicator lift: bound {lift['bound']}/{lift['base_unknowns']} "
              f"(bind rate {fmt(lift['bind_rate'])}, bind accuracy {fmt(lift['bind_accuracy'])})", ""]
    for name, r in results.items():
        lines.append(f"## {name} — confusion (rows=gold, cols=pred)")
        lines.append("| gold\\pred | " + " | ".join(CLASSES) + " |")
        lines.append("|---|" + "---|" * len(CLASSES))
        for g in CLASSES:
            lines.append(f"| {g} | " + " | ".join(str(r["confusion"][g][p]) for p in CLASSES) + " |")
        lines.append("")
        misses = {s: v["misses"] for s, v in r["per_stratum"].items() if v["misses"]}
        if misses:
            lines.append("Misses by stratum: " + json.dumps(misses))
            lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    schema, labels, cases = load_fixture()
    column = schema["subject"]["column"]
    dialect = schema["subject"].get("dialect", "snowflake")

    runs = {
        "B0 every-dependent-breaks": predict_b0(cases),
        "B1 substring-grep": predict_b1(cases, column=column),
        "C classifier": predict_classifier(cases, column=column, dialect=dialect),
        "C+A adjudicated": predict_adjudicated(cases, column=column, dialect=dialect, schema=schema),
    }
    results = {name: score(cases, preds) for name, preds in runs.items()}
    lift = adjudicator_lift(cases, runs["C classifier"], runs["C+A adjudicated"])

    if args.json:
        print(json.dumps({"results": results, "adjudicator_lift": lift}, indent=2))
    else:
        print(to_markdown(results, lift))


if __name__ == "__main__":
    main()
