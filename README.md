# Premortem

**how it breaks, before you merge**

Premortem is a schema-change rehearsal agent for [DataHub](https://datahub.com/).

When I propose renaming or dropping a column, Impact Analysis already tells me *what’s connected*. Premortem starts from that map and goes one layer deeper: it reads warehouse SQL from query history and forecasts *how* each consumer breaks — **hard**, **soft**, or **unknown** — then optionally writes the forecast back into the catalog so the next person (or agent) inherits it.

Built for the [DataHub Agent Hackathon](https://datahub.devpost.com/) (Apache-2.0).

## What you get

| Output | Meaning (remediation blast radius) |
|--------|--------------------------------------|
| **HARD** | Column in `WHERE` / `JOIN` / `GROUP BY` / `ORDER BY` / `HAVING` / window — repair can change row counts or results |
| **SOFT** | `SELECT`-list only — contained, mechanical rename downstream |
| **UNKNOWN** | Unparseable SQL, bare column still ambiguous after schema resolution, `SELECT *` — needs a human; never guessed |
| **UNAFFECTED** | No subject-bound reference — either **CLEARED** (same-named column binds elsewhere; listed) or no query evidence of the column (count) |

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

Offline folder of SQL (optional user-supplied baseline is labeled in the report):

```bash
premortem --queries-dir tests/fixtures/queries \
  --rename order_status:order_state \
  --lineage-count 12 \
  --out examples/forecast-offline.md
```

Live against DataHub (measured baseline only — `--lineage-count` is rejected with `--live`):

```bash
premortem --live --rename order_status:order_state \
  --out examples/forecast-order-status.md \
  --json-out examples/forecast-order-status.json

premortem --live --drop order_status \
  --out examples/forecast-drop-order-status.md

premortem --live --rename order_status:order_state --write-back
```

Set `DATAHUB_GMS_URL` (default `http://localhost:8080`) and `DATAHUB_GMS_TOKEN` when your GMS requires auth.

## Demo corpus

- [`examples/forecast-order-status.md`](examples/forecast-order-status.md) / [`.json`](examples/forecast-order-status.json)
- [`examples/forecast-drop-order-status.md`](examples/forecast-drop-order-status.md)
- Offline sample: [`examples/forecast-offline.md`](examples/forecast-offline.md)
- Live fallback seed: [`examples/seeded_queries.json`](examples/seeded_queries.json)
- Demo env seeder: [`tools/seed_demo_environment.py`](tools/seed_demo_environment.py)
- S2 assertion probe note: [`examples/S2_ASSERTION.md`](examples/S2_ASSERTION.md)

Frozen classifier fixtures: `tests/fixtures/queries/`. Frozen eval (honest numbers): [`eval/RESULTS.md`](eval/RESULTS.md).

## Limits (honest)

- Not 100% breakage prediction — macros, dynamic SQL, and residual ambiguity land in **unknown**
- No legal or compliance guarantees
- No query evidence ≠ safe to change
- The demo runs against a local DataHub Quickstart with the showcase-ecommerce datapack, extended with a synthetic `shipments` dataset, seeded query history, and seeded lineage. The accuracy numbers in [`eval/RESULTS.md`](eval/RESULTS.md) come from the frozen eval — not from this demo instance.
- Write-back demo beat is the **`premortem_forecast` tag** (+ editable description); Document create works but Quickstart often does not index it
- When running a DataHub MCP server on camera, set `DATAHUB_TELEMETRY_ENABLED=false` so `track.datahubproject.io` timeouts do not scroll the logs

## License

Apache-2.0 — see [`LICENSE`](LICENSE).
