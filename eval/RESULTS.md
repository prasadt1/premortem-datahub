# Eval results

Frozen corpus + labels: commit `5709e88` (labels sha256 `881892f2…`).
Harness is an adapter; this file records measurement against that freeze.
**Do not edit `eval/labels.json`.** Named limitations stay here.

Measured on binder commit `94949ba` (+ catalog facade thereafter does not change
classifier numbers). Re-run: `python eval/run_eval.py`.

## Headline metrics

| run | accuracy | HARD prec | HARD rec | UNKNOWN rate | decoy FP |
|---|---|---|---|---|---|
| B0 every-dependent-breaks | 0.40 | 0.40 | 1.00 | 0.00 | 1.00 |
| B1 substring grep | 0.45 | 0.44 | 1.00 | 0.00 | 0.83 |
| **C classifier (binder)** | **0.97** | **1.00** | **0.94** | 0.23 | **0.00** |
| C+A adjudicated (heuristic) | 0.90 | 0.88 | 0.94 | 0.15 | 0.00 |
| B2 LLM-on-residue (cached) | 0.97 | 1.00 | 0.94 | 0.23 | 0.00 |

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
| residue binds | — | 3/3 wrong | **0/3** (all left UNKNOWN) |
| bind accuracy | — | 0.00 | n/a (no binds) |

The model preferred “cannot determine” on every residue case — correct against
gold (`unknown`) and the opposite of the heuristic’s false confidence. B2 does
**not** beat binder-only on the headline metrics (it ties). Live default stays
**binder-only**; B2 ships available via cache but is not the default path.

“I tried the LLM on the residue and it refused to guess” is the published
result — a second honest negative relative to the hope that an LLM would clear
the UNKNOWN rate, and a positive relative to the heuristic.

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

## Reproduce

```bash
python eval/run_eval.py
# or
python eval/run_eval.py --json
```

Rebuild the LLM cache (requires Claude CLI; commit the file afterward):

```bash
python tools/build_llm_adjudicator_cache.py
```
