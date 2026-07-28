# Premortem

**how it breaks, before you merge**

Premortem is a schema-change rehearsal agent for [DataHub](https://datahub.com/).

When I propose renaming or dropping a column, Impact Analysis already tells me *what’s connected*. Premortem starts from that map and goes one layer deeper: it reads warehouse SQL from query history and forecasts *how* each consumer breaks — **hard**, **soft**, or **unknown** — then optionally writes the forecast back into the catalog so the next person (or agent) inherits it.

Built for the [DataHub Agent Hackathon](https://datahub.devpost.com/) (Apache-2.0).

## First 60 seconds

1. Install with the DataHub Kit + MCP extras, point at a local Quickstart, seed the demo env.
2. Ask an agent (Claude Code with both MCP servers registered) to rehearse renaming `order_status` → `order_state` on ORDER_HISTORY.
3. Watch the tool-call log: DataHub MCP for schema/lineage/queries, Premortem `rehearse_schema_change` for the forecast + `write_payload`.
4. On write-back, the host applies that payload as-is — custom assertion (camera hero on the Quality tab), `premortem_forecast` tag, description — no recomputing.

Frozen classifier evidence (C accuracy **0.97**, HARD prec **1.00**, decoy FP **0.00**) lives in [`eval/RESULTS.md`](eval/RESULTS.md). The live demo instance is constructed (synthetic shipments, seeded queries/lineage); the eval is the measurement.

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
pip install -e ".[dev,datahub,mcp]"
pytest -q
```

Live catalog default is the **DataHub Agent Kit** (`PREMORTEM_CATALOG=kit`). Explicit GraphQL fallback: `PREMORTEM_CATALOG=graphql` or `--catalog graphql`. Dual-MCP filming config: [`examples/MCP_COMPOSITION.md`](examples/MCP_COMPOSITION.md).

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

Set `DATAHUB_GMS_URL` (default `http://localhost:8080`) and `DATAHUB_GMS_TOKEN` when your GMS requires auth. Live defaults to binder-only (`adjudicate=False`); `--adjudicate` is opt-in and net-negative on the frozen eval.

Seed / refresh the constructed demo (idempotent; exactly one camera assertion):

```bash
python tools/seed_demo_environment.py
```

## Demo corpus

- [`examples/forecast-order-status.md`](examples/forecast-order-status.md) / [`.json`](examples/forecast-order-status.json)
- [`examples/forecast-drop-order-status.md`](examples/forecast-drop-order-status.md)
- Offline sample: [`examples/forecast-offline.md`](examples/forecast-offline.md)
- Live fallback seed: [`examples/seeded_queries.json`](examples/seeded_queries.json)
- Demo env seeder: [`tools/seed_demo_environment.py`](tools/seed_demo_environment.py)
- Camera assertion: [`examples/S2_ASSERTION.md`](examples/S2_ASSERTION.md)
- MCP composition (filming): [`examples/MCP_COMPOSITION.md`](examples/MCP_COMPOSITION.md)
- OSS Quickstart limits: [`examples/OSS_ISSUES.md`](examples/OSS_ISSUES.md)

Frozen classifier fixtures: `tests/fixtures/queries/`. Frozen eval (honest numbers): [`eval/RESULTS.md`](eval/RESULTS.md).

## Limits (honest)

- Not 100% breakage prediction — macros, dynamic SQL, and residual ambiguity land in **unknown**
- No legal or compliance guarantees
- No query evidence ≠ safe to change
- The demo runs against a local DataHub Quickstart with the showcase-ecommerce datapack, extended with a synthetic `shipments` dataset, seeded query history, and seeded lineage. The accuracy numbers in [`eval/RESULTS.md`](eval/RESULTS.md) come from the frozen eval — not from this demo instance.
- Write-back ladder (rung 1): custom **assertion** (platform `premortem`) + **`premortem_forecast` tag** + description. Document create may succeed without UI indexing on Quickstart.
- OSS MCP: Data Quality mutation tools are DISABLED — assertion upsert stays on GraphQL / seeder; host still applies tag + description via DataHub MCP.
- When running a DataHub MCP server on camera, set `DATAHUB_TELEMETRY_ENABLED=false` so `track.datahubproject.io` timeouts do not scroll the logs

## License

Apache-2.0 — see [`LICENSE`](LICENSE).
