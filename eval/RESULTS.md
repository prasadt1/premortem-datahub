# Eval results

Frozen corpus + labels: commit `5709e88` (labels sha256 `881892f2…`).
Harness is an adapter; this file records measurement against that freeze.
**Do not edit `eval/labels.json`.** Named limitations stay here.

Measured on binder commit `94949ba` (+ catalog facade thereafter does not change
classifier numbers). Headline metrics **re-verified unchanged** after Tier-1
refuse-instead-of-guess (no corpus query uses the newly refused shapes).
Re-run: `python eval/run_eval.py`.

**Discipline:** the binder was developed against `tests/` fixtures; the frozen forty
queries were never tuning targets. Measurement only: `python eval/run_eval.py`.

Corpus: **n=40**. Label provenance: three independent blind **LLM labeling runs**
(corpus + schema fixture + taxonomy only) agreed with the authored labels **40/40** —
see [`eval/README.md`](README.md).
## Headline metrics

| run | accuracy | HARD prec | HARD rec | UNKNOWN rate | decoy FP |
|---|---|---|---|---|---|
| B0 every-dependent-breaks | 0.40 | 0.40 | 1.00 | 0.00 | 1.00 |
| B1 substring grep | 0.45 | 0.44 | 1.00 | 0.00 | 0.83 |
| **C classifier (binder)** | **0.97** | **1.00** | **0.94** | 0.23 | **0.00** |
| C+A adjudicated (heuristic) | 0.90 | 0.88 | 0.94 | 0.15 | 0.00 |
| B2 LLM-on-residue (cached) | 0.97 | 1.00 | 0.94 | 0.23 | 0.00 |

**How to read the binder row.** Accuracy **0.97** is **39/40** — truncated, not rounded.
HARD precision **1.00** is over **n=15** predicted HARD (15/15 true positives; the one miss
is a gold HARD scored SOFT — q39 — so it never enters the precision denominator).
HARD recall **0.94** is 15/16 gold HARD. Decoy FP **0.00** is over the **n=6** decoy
stratum. UNKNOWN rate 0.23 is 9/40.

Before/after the multi-table binder (freeze baseline → binder):

| metric | freeze (C) | after binder (C) |
|---|---|---|
| accuracy | 0.65 | **0.97** |
| HARD precision | 0.77 | **1.00** |
| HARD recall | 0.62 | **0.94** |
| decoy FP rate | **0.50** | **0.00** |
| UNKNOWN rate | 0.38 | 0.23 |

## C+A is net-negative (published on purpose)

Heuristic adjudication binds **3 of 9** classifier UNKNOWNs (bind rate 0.33) with
**bind accuracy 0.00** — every bind is wrong:

| case | gold | C+A predicted |
|---|---|---|
| q05 | unknown | hard |
| q17 | unknown | soft |
| q29 | unknown | hard |

Those three are the entire `truly_ambiguous` stratum. Live/`--live` therefore
defaults to **`adjudicate=False`** (binder-only). `--adjudicate` without an
explicit LLM adjudicator still selects the net-negative heuristic. Shipping an
honest negative on our own component is intentional.

## B2 LLM-on-residue (measured)

Residue-only LLM adjudicator (`ResidueLlmAdjudicator`): runs **only** on genuine
multi-table bare-column UNKNOWNs (q05, q17, q29). Parse failures and `SELECT *`
are not sent to the model. Temperature-0 Claude CLI responses are committed in
[`eval/llm_adjudicator_cache.json`](llm_adjudicator_cache.json) so
`python eval/run_eval.py` reproduces B2 with **no API key**.

| metric | C binder | C+A heuristic | B2 LLM-on-residue |
|---|---|---|---|
| accuracy | **0.97** | 0.90 | **0.97** |
| residue decisions | — | 3/3 wrongly bound | **3/3 correctly declined** (left UNKNOWN) |

q05 / q17 / q29 are *genuinely undecidable* — their gold **is** `unknown`. The
model correctly refused all three, which is the designed behavior (an
adjudicator that can say “cannot determine” and does). Accuracy does not rise
because the gold was already UNKNOWN; the LLM adds **no measurable lift** on
this corpus, so it is not worth making a live dependency. Live default stays
**binder-only**.

Relative to the heuristic’s false confidence this is a win; relative to the
hope that an LLM would clear the UNKNOWN rate, it is an honest negative —
published as such.

## Named C miss (do not “fix” from the answer key)

**q39 (`hard` → `soft`)** — subquery stratum. Outer `IN` is fed by a subquery that
*projects* `order_status`; the binder currently treats that projection as SOFT.
Gold is HARD (filter participation at depth). There is no `tests/` fixture for
this shape; fixing it against `eval/labels.json` would violate freeze discipline.
Documented limitation for the video receipts beat (“misses included”).

No other C stratum misses on this run.

## Demo beats (verified against live path)

With binder + `adjudicate=False` default:

1. **Cleared false alarm** — `decoy_shipments_order_status` → UNAFFECTED / `BOUND_ELSEWHERE:shipments`, rendered under **CLEARED**
2. **Honest UNKNOWN** — `unknown_bare_two_tables` stays UNKNOWN (not emptied by the
   tautological adjudicator)

## Repair round-trip (does not touch the freeze)

`python eval/run_repair_roundtrip.py` rewrites every binder HARD/SOFT corpus query
(`order_status` → `order_state`), then re-classifies: old column → UNAFFECTED; new
column → original severity. CLEARED / UNKNOWN / SELECT * / cannot-verify-under-star
are **refused** (no patch) — the honesty identity extended into repair. Labels,
schema, and corpus stay byte-identical.

q25 (HARD WHERE + CTE `SELECT *`) is refused as *"cannot verify completeness
(star may still reference the old column)"* — the rename of the enumerated ref may
be semantically complete, but under a star we cannot attest that, and this product
does not ship unverified patches.

| metric | n |
|---|---:|
| patched (eligible) | 22 |
| round-trip pass | **22/22** |
| refused | 18 |
| — ambiguous binding (incl. 4 unparseable) | 7 |
| — CLEARED (binds elsewhere) | 4 |
| — no subject-bound reference | 4 |
| — SELECT * over subject | 2 |
| — cannot verify completeness (star) | 1 |

Kill criterion met: **100%** of emitted patches round-trip. Sample diffs:
[`examples/patches/`](../examples/patches/).

## Known blind spots of this corpus

The frozen forty contain **no** cross-scope alias shadowing, **no** derived-table
aliases, and **no** DML (`UPDATE` / `INSERT` column lists / `MERGE … SET`). Those
classes are covered in `tests/test_binder_tier1_safety.py` only — found by
adversarial review after the freeze. Tier-1 binder policy for them is **refuse
instead of guess** (UNKNOWN / no patch), not a claim of full resolution.
`0.97 / 1.00 / 0.00` remains an accurate measurement of what the corpus measures.

## What's next

Per-scope binding via sqlglot's scope resolver — today those shapes are
**refused rather than guessed** (Tier 1). Elective: convert declines back into
correct verdicts only when eval and round-trip stay bit-identical.

## Reproduce

```bash
python eval/run_eval.py
python eval/run_repair_roundtrip.py
# or
python eval/run_eval.py --json
```

Rebuild the LLM cache (requires Claude CLI; commit the file afterward):

```bash
python tools/build_llm_adjudicator_cache.py
```
