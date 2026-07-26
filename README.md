# Premortem

**how it breaks, before you merge**

Before you merge a schema change, Premortem extends DataHub Impact Analysis: not only *what* is connected, but *how* each consumer breaks — **hard**, **soft**, or **unknown** — from real warehouse SQL.

Built for the [DataHub Agent Hackathon](https://datahub.devpost.com/) (Apache-2.0).

## Status

- Thesis locked; core sqlglot classifier scaffolds without live DataHub.
- MCP write-back and live E2E blocked until gates in [`VERIFY.md`](VERIFY.md) pass.

## Quick start (core)

Requires Python 3.11+.

```bash
/opt/homebrew/bin/python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
premortem --sql-file tests/fixtures/queries/hard_where.sql --column order_status
```

## Do not claim

- 100% breakage prediction
- Legal/compliance guarantees
- Catalog write-back until Gate 1 is green

## Docs

- Design: [`docs/superpowers/specs/2026-07-26-datahub-schema-rehearsal-design.md`](docs/superpowers/specs/2026-07-26-datahub-schema-rehearsal-design.md)
- Plan: [`docs/superpowers/plans/2026-07-26-datahub-schema-rehearsal.md`](docs/superpowers/plans/2026-07-26-datahub-schema-rehearsal.md)
