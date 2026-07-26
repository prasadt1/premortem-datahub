# DataHub Schema-Change Rehearsal Agent — Design

**Date:** 2026-07-26 (rev: research consensus + verify reorder)  
**Hackathon:** Build with DataHub: The Agent Hackathon (due Aug 10, 2026)  
**Category:** Agents That Do Real Work (+ sample artifacts for judges)  
**Status:** Locked thesis · verification-gated · unknown-bucket + write-back path required before MCP integration

---

## 1. One-liner

An agent that takes a **proposed schema change**, starts from Impact Analysis-style lineage (“what’s connected”), then goes one layer deeper using real SQL query history to emit a ranked **break-forecast** (hard / soft / **unknown**) — and, *if write-back is confirmed on this instance*, writes that forecast back into the catalog.

## 2. Protagonist and stakes

**Protagonist:** a data engineer about to merge a column rename or drop.

**Stakes:** last time this silently broke Looker explores and a dbt model on Friday deploy. Knowing *what* is connected wasn’t enough; they needed *how* each consumer breaks — and what the classifier cannot tell.

## 3. Verification gates (ordered by blast radius)

Do **not** wire MCP write-back or claim write-back in README/video until Gate 1 passes.

| # | Gate | Pass condition | Fail action |
|---|------|----------------|-------------|
| **1** | **Write-back path** | On *your* instance (OSS Quickstart + self-hosted MCP **or** Cloud), at least one of `add_tags` / `update_description` / `save_document` (or GraphQL equivalent) mutates an entity you can see in the UI | Self-host MCP with mutations enabled, **or** cut write-back from demo/claims and score on forecast artifact + frozen eval only |
| **2** | Query history | `get_dataset_queries` returns real SQL for demo URN after `showcase-ecommerce` load | Seed via `sql-queries` or switch to Gamma |
| **3** | Exec counts (§3.4) | Inspect payload for count fields | Rank hard→soft only; never invent `(exec×N)` |
| **4** | Impact Analysis compose check | UI still lists dependents without breakage modes | If shipped product already does hard/soft classify, kill A → Gamma |

**Bootstrap:**

```bash
datahub docker quickstart
datahub init --username datahub --password datahub
datahub datapack load showcase-ecommerce
# Then: self-host mcp-server-datahub OR use Cloud MCP — confirm mutations
```

Managed MCP / AI Documentation may be Cloud-only (v0.3.12+ / v0.3.17+). OSS = self-host MCP + tokens. Confirm live; do not trust research alone.

### 3.2 Impact Analysis — compose, don’t critique

**Demo / README framing (mandatory):**

> Impact Analysis tells me *what’s* connected — N dependents. I start there and go one layer deeper: *how* each one breaks — and what I still don’t know.

Do **not** demo “Impact Analysis is insufficient.”

### 3.3 Load-bearing differentiator

| Claim | Keep? |
|-------|-------|
| **Query-level hard / soft / unknown** | **★ Must ship** |
| Proposed diff (predictive) | Framing |
| Write-back | Scoring bonus — **Gate 1 contingent** |
| PR loop | Cut first under pressure |

### 3.4 Usage / execution counts

Only print `(exec×N)` if Gate 3 passes. Otherwise omit.

### 3.5 Do not claim (verbatim from research consensus)

- No **100% breakage prediction** (dbt macros / dynamic SQL / unparseable queries → **unknown**)
- No compliance/legal guarantees
- No unverified Cloud-only features as if they work on OSS Quickstart

---

## 4. Product behavior

### Input

- Dataset URN (or search-resolved name)
- `rename` (`old:new`) or `drop` (`column`) — `type_change` deferred from v1

### Classification taxonomy (core)

| Severity | Meaning |
|----------|---------|
| **HARD** | Column in `JOIN` / `WHERE` / `GROUP BY` / `ORDER BY` / `HAVING` / window `PARTITION BY` |
| **SOFT** | Column only in `SELECT` list |
| **UNKNOWN** | Unparseable SQL, dialect failure, unqualified name with >1 table in scope, or insufficient evidence — **needs human** |
| **UNAFFECTED** | No reference found (lineage neighbor with no query hit) |

**Rule:** unqualified identifier equal to target column + >1 table in scope → **UNKNOWN** (not HARD). Agent may later adjudicate UNKNOWN → HARD/SOFT with an `agent_note`; core never invents certainty.

### Process

1. Confirm column via `list_schema_fields`.
2. Downstream lineage = Impact Analysis baseline (“what’s connected”).
3. `get_dataset_queries` → SQL corpus.
4. **sqlglot core:** detect + HARD/SOFT/UNKNOWN (deterministic, tested).
5. **Agent:** adjudicate UNKNOWN where schema/lineage allows; optionally deepen queries on heavy consumers; compose forecast (+ write-back **iff Gate 1**).
6. Rank: HARD → SOFT → UNKNOWN; within tier by exec count only if Gate 3.
7. Emit markdown + JSON artifacts (always).
8. Write-back only if Gate 1.

### Output shape

```text
Schema rehearsal: orders.order_status → rename to order_state

Impact Analysis baseline: 12 downstream dependents

HARD (2)
- …

SOFT (2)
- …

UNKNOWN / needs human (3)
- q:… — parse error / bare column in 4-table join — reason: …

UNAFFECTED (no query evidence): 5
```

`examples/` frozen forecasts required for judges who won’t run the stack.

---

## 5. Architecture

```text
Agent (adjudicate UNKNOWN, deepen, compose)
        │ MCP read (+ write iff Gate 1)
        ▼
DataHub (lineage, queries, optional write-back)
        ▲
Core (sqlglot HARD/SOFT/UNKNOWN) ← unit-tested, no live DataHub
```

| Layer | Owns |
|-------|------|
| Core | Candidate hits + HARD/SOFT/UNKNOWN |
| Agent | Adjudication, deepen, narrative, optional write-back |

---

## 6. Tech choices

| Piece | Choice |
|-------|--------|
| Catalog | Quickstart + `showcase-ecommerce` |
| Agent I/O | MCP (self-hosted OSS or Cloud) — verify mutations |
| Parse | sqlglot |
| Write-back | Gate 1 tools only; verify live names |
| Demo | CLI `rehearse` |

**Non-goals v1:** PR-comment bot, type_change, claiming perfect SQL semantics.

---

## 7. Demo script

1. Proposed rename on showcase column with HARD + SOFT + UNKNOWN evidence.
2. Compose Impact Analysis: “N dependents — starting map.”
3. Rehearsal: HARD/SOFT + one UNKNOWN (and optional agent adjudication).
4. Write-back **only if Gate 1** — else end on forecast artifact + frozen eval numbers.
5. Point at `examples/` + published classifier metrics.

---

## 8. Eval / honesty

- Frozen labeled fixtures committed **before** tuning (Claude designs eval after Gates 1–3 results).
- Publish precision/recall **including** UNKNOWN rate and false positives on bare columns.
- Limits: UNKNOWN ≠ safe; no query evidence ≠ safe; agent can mis-adjudicate.

---

## 9. Slices (dated)

| Slice | Done by | Notes |
|-------|---------|-------|
| Gates 1–3 (human) | **today / Jul 28** | Blocks MCP write path |
| Platform-agnostic core + tests | **Aug 2** | Safe in parallel now |
| Agent + MCP read (+ write if Gate 1) | **Aug 5** | |
| examples/ + optional write-back | **Aug 6–7** | |
| README + video | **Aug 8** | |
| Buffer | **Aug 9–10** | Protect Cockroach |

---

## 10. Kill criteria

- Gate 2 fails and seeding fails → Gamma  
- Gate 4 fails (shipped breakage classify) → Gamma  
- Gate 1 fails → **do not kill thesis**; cut write-back claim, keep forecast + eval

---

## 11. Parallel (you / not Cursor)

- Bedrock region + model request **today**  
- Cockroach: `CREATE VECTOR INDEX` smoke + `SHOW ZONE CONFIGURATION` for GC TTL  
- Cockroach Managed MCP is read-only by default — consent scopes for writes later
