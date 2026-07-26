# Premortem

**how it breaks, before you merge**

Premortem is a schema-change rehearsal agent for [DataHub](https://datahub.com/).

When I propose renaming or dropping a column, Impact Analysis already tells me *what’s connected*. Premortem starts from that map and goes one layer deeper: it reads real warehouse SQL from query history and forecasts *how* each consumer breaks — **hard**, **soft**, or **unknown** — then optionally writes the forecast back into the catalog.

Built for the [DataHub Agent Hackathon](https://datahub.devpost.com/) (Apache-2.0).

## What you get

| Output | Meaning |
|--------|---------|
| **HARD** | Column used in `JOIN` / `WHERE` / `GROUP BY` / `ORDER BY` / … — query likely fails or filters wrong |
| **SOFT** | Column only projected in `SELECT` — shape/semantics drift |
| **UNKNOWN** | Unparseable SQL, bare column with multiple tables in scope, or not enough evidence — needs a human (or agent adjudication) |
| **UNAFFECTED** | No reference to the column in that query |

Forecasts are ranked HARD → SOFT → UNKNOWN, composed under an Impact Analysis baseline (“N downstream dependents”), and emitted as markdown + JSON. I do **not** invent execution counts; `(exec×N)` appears only when the catalog actually provides them.

## Install

Python 3.11+:

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

## Usage

Classify one query:

```bash
premortem --sql-file tests/fixtures/queries/hard_where.sql --column order_status
```

Rehearse a rename over a folder of SQL (offline fixtures or exported history):

```bash
premortem --queries-dir tests/fixtures/queries \
  --rename order_status:order_state \
  --lineage-count 12 \
  --out examples/forecast-offline.md
```

Upgrade UNKNOWN findings with the agent binder (heuristic by default — no API key):

```bash
premortem --queries-dir tests/fixtures/queries \
  --rename order_status:order_state \
  --lineage-count 12 \
  --adjudicate \
  --schema-fields id,order_status,customer_id
```

Drop is the same pipeline:

```bash
premortem --queries-dir tests/fixtures/queries --drop order_status
```

Write the forecast back to DataHub (tag / description / document on your instance):

```bash
premortem --queries-dir tests/fixtures/queries \
  --rename order_status:order_state \
  --urn 'urn:li:dataset:(…)' \
  --write-back
```

Set `DATAHUB_GMS_URL` (default `http://localhost:8080`) and `DATAHUB_GMS_TOKEN` when your GMS requires auth.

## Demo corpus

Sample forecast: [`examples/forecast-offline.md`](examples/forecast-offline.md).

Frozen SQL fixtures under `tests/fixtures/queries/` drive the deterministic sqlglot classifier. For a live DataHub demo against showcase-style `ORDER_HISTORY.order_status`, see [`examples/seeded_queries.json`](examples/seeded_queries.json).

## Limits (honest)

- Not 100% breakage prediction — macros, dynamic SQL, and ambiguous bindings land in **unknown**
- No legal or compliance guarantees
- No query evidence ≠ safe to change

## License

Apache-2.0 — see [`LICENSE`](LICENSE).
