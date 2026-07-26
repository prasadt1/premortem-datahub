# Schema-Change Rehearsal Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a DataHub agent that extends Impact Analysis with query-level breakage forecasts (hard/soft/**unknown** → LLM adjudicates) and optionally writes the forecast back — before Aug 10, 2026.

**Architecture:** Deterministic `rehearsal` core (sqlglot) is unit-tested with **no live DataHub**. MCP agent + write-back only after Gate 1.

**Tech Stack:** Python 3.11+, sqlglot, pytest, DataHub MCP (self-hosted or Cloud), LLM host for agent.

**Spec:** `docs/superpowers/specs/2026-07-26-datahub-premortem-design.md`  
**Cockroach spec (later):** `docs/superpowers/specs/2026-07-26-cockroach-vector-shredder-design.md`

**Labor:** Cursor builds; human runs access gates; Claude reviews at seams (eval design after Gates 1–3).

**Verify order (human — blast radius):**
1. DataHub **write-back** on your path (Cloud vs self-hosted OSS MCP) ← blocks write-back claims  
2. `get_dataset_queries` SQL on `showcase-ecommerce`  
3. Exec-count surface (§3.4)  
4. Cockroach `CREATE VECTOR INDEX` + live GC TTL  
5. Bedrock region+model request (queue — do today)

**Parallel-safe now (no live DataHub required):** Tasks 1, 3, 4, 5 (scaffold, models, classify, rank/report).  
**Blocked until Gate 1:** write-back implementation and demo beat claiming catalog mutation.  
**Blocked until Gate 2:** live E2E against showcase URN.

**Dates:** Core Aug 2 · E2E Aug 5 · Write-back Aug 6–7 (if Gate 1) · README/video Aug 8 · Buffer Aug 9–10.

---

## File structure (new project root)

Create under `/Users/prasadt1/Datahub-CockroachDB-hackathon-ideation/premortem/`:

```text
premortem/
  pyproject.toml
  README.md
  LICENSE                    # Apache-2.0 (hackathon requirement)
  src/premortem/
    __init__.py
    models.py                # Diff, BreakSeverity, BreakFinding, Forecast
    classify.py              # sqlglot: detect + hard/soft/ambiguous
    rank.py                  # hard>soft; optional exec counts
    report.py                # markdown + JSON emitters
    datahub_client.py        # thin MCP/HTTP wrapper for tools used
    agent.py                 # LLM loop: adjudicate, deepen, write-back
    cli.py                   # `rehearse` entrypoint
  tests/
    fixtures/queries/        # frozen SQL + expected labels
    test_classify.py
    test_rank.py
    test_report.py
  examples/
    forecast-order-status.md
    forecast-order-status.json
```

---

### Task 1: Scaffold project + Apache-2.0

**Files:**
- Create: `premortem/pyproject.toml`
- Create: `premortem/LICENSE`
- Create: `premortem/src/premortem/__init__.py`
- Create: `premortem/README.md` (stub)

- [ ] **Step 1: Create package layout and pyproject**

```toml
[project]
name = "premortem"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "sqlglot>=25.0.0",
  "httpx>=0.27.0",
  "pydantic>=2.0",
]
[project.optional-dependencies]
dev = ["pytest>=8.0"]
[project.scripts]
rehearse = "premortem.cli:main"
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
```

- [ ] **Step 2: Add Apache-2.0 LICENSE file** (hackathon requires detectable OSS license)

- [ ] **Step 3: Commit**

```bash
cd /Users/prasadt1/Datahub-CockroachDB-hackathon-ideation
git init  # if not already a repo
git add premortem
git commit -m "chore: scaffold premortem package"
```

---

### Task 2: Bootstrap DataHub + verify queries and exec counts (by Jul 28)

**Files:**
- Create: `premortem/scripts/smoke_queries.py`
- Modify: `premortem/README.md` (bootstrap section)

- [ ] **Step 1: Start Quickstart and load datapack**

```bash
datahub docker quickstart
datahub init --username datahub --password datahub
datahub datapack load showcase-ecommerce
```

Expected: load completes; UI at http://localhost:9002

- [ ] **Step 2: Smoke `get_dataset_queries` (MCP or GraphQL)**

Pick a Snowflake orders-related URN from the pack (confirm in UI). Call `get_dataset_queries` (or GraphQL `listQueries` / dataset queries field). Assert ≥1 SQL strings returned.

- [ ] **Step 3: §3.4 execution-count gate**

Inspect one query payload for `queryCountLast30Days`, `queryCountTotal`, or equivalent. Record decision in `README.md`:

- `RANK_BY_EXEC_COUNT=true` and show `(exec×N)`, **or**
- `RANK_BY_EXEC_COUNT=false` and never print frequency.

- [ ] **Step 4: Lock demo column**

Choose a column that appears in both WHERE/filter queries and SELECT-only queries (e.g. `order_status` if present in pack SQL). Write URN + column into `examples/DEMO.md`.

- [ ] **Step 5: Commit**

```bash
git add premortem/scripts premortem/README.md premortem/examples/DEMO.md
git commit -m "docs: lock demo URN, column, and exec-count ranking policy"
```

---

### Task 3: Domain models

**Files:**
- Create: `src/premortem/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing import/construction test**

```python
from premortem.models import BreakSeverity, BreakFinding, SchemaDiff, Forecast

def test_break_finding_requires_severity():
    f = BreakFinding(
        query_id="q1",
        sql_snippet="WHERE order_status = 1",
        severity=BreakSeverity.HARD,
        column="order_status",
        evidence="WHERE",
    )
    assert f.severity is BreakSeverity.HARD
```

- [ ] **Step 2: Implement models**

```python
from enum import Enum
from pydantic import BaseModel

class BreakSeverity(str, Enum):
    HARD = "hard"
    SOFT = "soft"
    AMBIGUOUS = "ambiguous"
    UNAFFECTED = "unaffected"

class SchemaDiff(BaseModel):
    dataset_urn: str
    kind: str  # rename | drop | type_change
    column: str
    new_column: str | None = None
    new_type: str | None = None

class BreakFinding(BaseModel):
    query_id: str
    sql_snippet: str
    severity: BreakSeverity
    column: str
    evidence: str
    exec_count: int | None = None
    agent_note: str | None = None

class Forecast(BaseModel):
    diff: SchemaDiff
    lineage_dependent_count: int
    findings: list[BreakFinding]
    unaffected_lineage_count: int = 0

class QueryRecord(BaseModel):
    """Normalized row from get_dataset_queries / GraphQL — required fields locked here."""
    query_id: str
    sql: str
    dataset_urn: str | None = None  # subject / consumer if API provides it
    exec_count: int | None = None   # only set when live API returns a count (§3.4)
```

- [ ] **Step 3: Run tests — expect PASS**

```bash
cd premortem && pip install -e ".[dev]" && pytest tests/test_models.py -v
```

- [ ] **Step 4: Commit**

```bash
git commit -am "feat: add forecast domain models"
```

---

### Task 4: sqlglot classifier (core — due Aug 2)

**Files:**
- Create: `src/premortem/classify.py`
- Create: `tests/fixtures/queries/hard_where.sql`
- Create: `tests/fixtures/queries/soft_select.sql`
- Create: `tests/fixtures/queries/ambiguous_bare.sql`
- Create: `tests/test_classify.py`

- [ ] **Step 1: Write failing tests for hard / soft / ambiguous**

```python
from premortem.classify import classify_query
from premortem.models import BreakSeverity

def test_where_is_hard():
    sql = "SELECT id FROM orders WHERE order_status = 1"
    r = classify_query(sql, column="order_status", dialect="snowflake")
    assert r.severity is BreakSeverity.HARD
    assert "WHERE" in r.evidence

def test_select_only_is_soft():
    sql = "SELECT order_status, id FROM orders"
    r = classify_query(sql, column="order_status", dialect="snowflake")
    assert r.severity is BreakSeverity.SOFT

def test_bare_column_in_multi_table_join_is_ambiguous():
    sql = """
    SELECT o.id, c.name FROM orders o
    JOIN customers c ON o.customer_id = c.id
    WHERE order_status = 1
    """
    r = classify_query(sql, column="order_status", dialect="snowflake")
    # Rule (locked): unqualified identifier equal to target column, >1 table in scope → AMBIGUOUS
    assert r.severity is BreakSeverity.AMBIGUOUS
```

Ambiguity rule is locked: do not also assert HARD for this case — agent upgrades severity later.

- [ ] **Step 2: Run tests — expect FAIL**

```bash
pytest tests/test_classify.py -v
```

- [ ] **Step 3: Implement `classify_query` with sqlglot**

Walk the AST; record clause context for column hits; return `BreakFinding`-like result (or a small `ClassifyResult` dataclass). No LLM calls here.

- [ ] **Step 4: Run tests — expect PASS**

- [ ] **Step 5: Add 5–10 fixture SQL files from showcase-like patterns; freeze expected labels in `tests/fixtures/expected.json`**

- [ ] **Step 6: Commit**

```bash
git commit -am "feat: sqlglot hard/soft/ambiguous column usage classifier"
```

---

### Task 5: Rank + report emitters

**Files:**
- Create: `src/premortem/rank.py`
- Create: `src/premortem/report.py`
- Create: `tests/test_rank.py`
- Create: `tests/test_report.py`

- [ ] **Step 1: Tests — hard before soft; exec_count sort only when all relevant findings have counts**

```python
def test_rank_hard_before_soft_without_counts():
    # ... findings with exec_count=None → stable hard-then-soft, no crash
```

- [ ] **Step 2: Implement `rank_findings(findings, use_exec_count: bool)`**

- [ ] **Step 3: Implement `to_markdown(forecast)` and `to_json(forecast)`**

Markdown must include Impact Analysis baseline line (“N downstream dependents”) then breakage sections. Omit `(exec×N)` when `exec_count` is None.

- [ ] **Step 4: pytest green; commit**

```bash
git commit -am "feat: rank findings and emit markdown/json forecasts"
```

---

### Task 6: DataHub client wrapper

**Files:**
- Create: `src/premortem/datahub_client.py`
- Create: `tests/test_datahub_client.py` (mock httpx / MCP)

- [ ] **Step 1: Define minimal interface**

```python
from premortem.models import QueryRecord

class DataHubClient(Protocol):
    def list_schema_fields(self, urn: str) -> list[str]: ...
    def get_downstream(self, urn: str, column: str | None = None) -> list[str]: ...
    def get_dataset_queries(self, urn: str) -> list[QueryRecord]: ...
    def save_forecast_document(self, urn: str, title: str, body_md: str) -> str: ...
    def add_tags(self, urn: str, tag_urns: list[str]) -> None: ...
```

Map MCP/GraphQL payloads into `QueryRecord` explicitly. If the API omits execution counts, leave `exec_count=None` — never fabricate.

- [ ] **Step 2: Implement against live MCP or GraphQL** — verify exact tool/mutation names against the running instance (do not trust docs alone for write-back).

- [ ] **Step 3: Integration smoke (manual OK): fetch queries for demo URN**

- [ ] **Step 4: Commit**

```bash
git commit -am "feat: DataHub client for lineage, queries, and write-back"
```

---

### Task 7: Agent loop — adjudicate + deepen + compose (E2E by Aug 5)

**Files:**
- Create: `src/premortem/agent.py`
- Create: `src/premortem/cli.py`
- Create: `tests/test_agent_adjudication.py` (mock LLM)

- [ ] **Step 1: Failing test — ambiguous finding becomes HARD or SOFT after agent note**

Mock LLM returns structured adjudication for one ambiguous SQL; assert `agent_note` set and severity updated.

- [ ] **Step 2: Implement agent**

Responsibilities only:
1. Run core classify over query set.
2. For each `AMBIGUOUS`, call LLM with SQL + schema fields + lineage neighbors; accept/reject binding.
3. Optionally call `get_dataset_queries` on a downstream URN if lineage shows a heavy consumer with no queries yet.
4. Build `Forecast`; do not invent exec counts.

- [ ] **Step 3: Wire CLI** — support both required change kinds; defer `type_change` from v1

```bash
# rename (primary demo)
rehearse --urn "urn:li:dataset:..." --rename order_status:order_state --out examples/forecast-order-status.md

# drop (required by spec; same pipeline, severity rules unchanged)
rehearse --urn "urn:li:dataset:..." --drop order_status --out examples/forecast-drop-order-status.md
```

`--rename` and `--drop` are mutually exclusive. `type_change` is explicitly **out of v1** (optional in spec) — do not implement CLI for it.

- [ ] **Step 4: Live E2E on showcase demo column — produce real forecast file** (at least one `--rename` run; one `--drop` smoke if time)

- [ ] **Step 5: Commit**

```bash
git commit -am "feat: agent adjudicates ambiguous columns and emits forecast"
```

---

### Task 8: Write-back + frozen examples (Aug 6–7)

**Files:**
- Modify: `src/premortem/agent.py` / `cli.py` (`--write-back` flag)
- Create: `examples/forecast-order-status.md`
- Create: `examples/forecast-order-status.json`

- [ ] **Step 1: Implement write-back** via verified MCP tools (`save_document` and/or `add_tags` / `update_description`)

- [ ] **Step 2: Run once with `--write-back`; screenshot or note UI location for video**

- [ ] **Step 3: Freeze successful artifacts into `examples/` (checked into git)**

- [ ] **Step 4: Commit**

```bash
git commit -am "feat: write forecast back to DataHub; freeze example artifacts"
```

---

### Task 9: README + submission packaging (Aug 8)

**Files:**
- Modify: `README.md`
- Create: `docs/LIMITATIONS.md` (optional short section inside README instead)

- [ ] **Step 1: Write README with compose framing**

Must include: one-liner, protagonist, “extends Impact Analysis” sentence, setup, demo URN/column, how to run, limitations (§8), link to `examples/`.

- [ ] **Step 2: Record ≤3 min video** following §7 demo script (compose, don’t critique)

- [ ] **Step 3: Public GitHub repo + Apache-2.0 visible; Devpost draft fields ready**

- [ ] **Step 4: Commit**

```bash
git commit -am "docs: submission README and limitations"
```

---

### Task 10: Buffer only (Aug 9–10)

- [ ] **Step 1: Fix bugs from dry-run judging only**
- [ ] **Step 2: Do not add PR-comment formatter, UI polish, or new features**
- [ ] **Step 3: Confirm Cockroach Bedrock region/model access already requested; scratch `CREATE VECTOR INDEX` if not done**

---

## Out of scope (do not schedule)

- PR comment bot / GitHub App
- Rebuilding Impact Analysis UI
- Claiming GDPR or perfect SQL semantics
- Parallel Cockroach implementation before Aug 10 ship
