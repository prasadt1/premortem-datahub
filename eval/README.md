# Frozen eval

Measures the classifier (and the adjudicated pipeline) against hand-labeled ground
truth that was **committed before any classifier or binder tuning**. The labels never
change after this freeze; only `RESULTS.md` gets added (drafted after binder P0;
B2/LLM row may update later). If a label turns out to be
wrong, the erratum is documented in `RESULTS.md` — the label file stays as frozen.

**Subject:** rename `analytics.order_history.order_status` → `order_state` (Snowflake).
The schema fixture (`schema.json`) defines which tables carry which columns — required
to make "resolves to exactly one table" well-defined.

## What's here

| File | Role |
|---|---|
| `corpus/q01.sql … q40.sql` | 40 queries, neutral filenames, strata interleaved (names/order leak nothing) |
| `schema.json` | Table → columns fixture + subject definition |
| `labels.json` | Gold verdict + stratum + rationale per query (frozen) |
| `run_eval.py` | Harness: B0/B1/C/C+A runs, confusion matrices, headline metrics. An **adapter** — it may evolve (e.g., when the multi-table binder lands); corpus+labels may not. |

## Strata (n=40)

| Stratum | n | Tests |
|---|---|---|
| unambiguous_hard | 8 | Baseline competence: WHERE/JOIN/GROUP/ORDER/HAVING/QUALIFY/window/CASE-in-WHERE |
| unambiguous_soft | 5 | Projection-only, incl. alias and expression projections |
| narrowable | 3 | Bare column, multi-table, only subject carries it → deterministic bind |
| truly_ambiguous | 3 | Bare column, ≥2 in-scope tables carry it → must stay UNKNOWN |
| decoy | 6 | Same-named column on other tables, literals, comments → false-positive detector (gold UNAFFECTED) |
| select_star | 4 | Star over subject → UNKNOWN; **traps:** star over non-subject → UNAFFECTED (q13), `COUNT(*)`+WHERE → HARD (q35) |
| cte_single_source | 4 | CTEs must not count as extra tables; includes an UNAFFECTED trap (q36) |
| unparseable | 4 | dbt/jinja, placeholders, truncated log SQL → UNKNOWN (parse failure empirically verified) |
| subquery | 3 | Correlated EXISTS/scalar, projection-feeding-IN → filter participation at depth |

Gold distribution: 16 hard / 7 soft / 9 unknown / 8 unaffected.

## Metrics (see `run_eval.py`)

Headline: **HARD precision** (cry-wolf), **HARD recall** (Friday-outage), **UNKNOWN rate**
(the honesty dial — never tuned down), **decoy false-positive rate**, and **adjudicator
bind-rate + bind-accuracy** (binding often is worthless if binding wrong).

Baselines: **B0** every-IA-dependent-breaks (the bar Impact Analysis alone implies) ·
**B1** substring grep (proves the AST earns its dependency) · **C** classifier ·
**C+A** classifier + adjudication (isolates the agent's contribution).

## How the labels were made (verification protocol)

1. Labels authored per the approved taxonomy (remediation blast radius; spec §1) with a
   sha256 recorded before any external review.
2. **Three independent labelers** labeled all 40 queries blind — given only the corpus,
   the schema fixture, and the taxonomy; barred from the rest of the repo. Result:
   **40/40 agreement with the authored labels, from all three** (no adjudication needed).
3. A parse sweep confirmed exactly the four `unparseable`-stratum files fail
   `sqlglot.parse_one(..., read="snowflake")` (sqlglot 30.13.0) and the other 36 parse.
4. A leakage check against `tests/fixtures/queries/` and `examples/seeded_queries.json`
   flagged three near-duplicates of the demo seed corpus (q01, q03, q10); all three were
   rewritten to structurally distinct SQL (same stratum and gold role) and re-verified
   blind by three fresh labelers. Rule: `tests/` locks behavior, `eval/` measures it,
   the demo seed is neither — no shared SQL across the three.

## Documented taxonomy decisions (from independent-labeler review)

- **Templates are judged as raw ingested SQL.** q09 would be HARD and q31 SOFT after
  jinja rendering; the eval scores what query history actually contains — unrendered
  text → UNKNOWN. Post-render adjudication is roadmap, and this conservatism is
  counted against us in the published numbers.
- **Ambiguous bare columns (q05/q17/q29) would error at Snowflake compile time.** The
  eval models catalog-time reality: query history contains SQL written before
  `logistics.shipments.order_status` existed; the catalog sees ambiguity the warehouse
  never did. That is precisely the case the binder must refuse to guess on.
- **Expression projections count as SOFT** (q30 `UPPER(...)`, q40 `CASE ... END` in the
  SELECT list): classification is by syntactic role, not by what downstream consumers
  might do with the projected value — that uncertainty exists for every projection.
- **Qualified star over the subject (q24 `o.*`) is UNKNOWN, not SOFT.** A defensible
  alternate reading is SOFT (star expansion is projection); the taxonomy deliberately
  prefers needs-a-human over a guess. Conservatism is a feature; it is also honestly
  reported as a higher UNKNOWN rate.
- **q39 compares `tickets.priority` to `order_status` values** — semantically odd but
  it parses, binds, and filters; labeled HARD per filter participation. Query history
  contains semantically odd SQL.
- **q37's verdict rests on the `${...}` token** (sqlglot's snowflake dialect rejects it;
  `:status_param` alone would parse). A pipeline that substitutes template variables
  before parsing would read the query as HARD via its WHERE — same rendering caveat as
  q09/q31, flagged independently by all three re-verification labelers.

## Freeze discipline

- The freeze is the git commit adding this directory; `labels.json` sha256 is recorded
  in the commit message and in `RESULTS.md`.
- The implementing agent must not consult `labels.json` while tuning the classifier or
  binder. Tuning targets are the (already-burned) regression tests in `tests/`; this
  eval is measurement, not feedback.
- `RESULTS.md` reports every run — including the pre-fix baseline — with misses left in.
