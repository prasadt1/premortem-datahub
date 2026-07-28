# Real-world run - mozilla/bigquery-etl

> **Not the frozen eval.** There are no gold labels on this corpus, so this report does **not** claim accuracy, precision, or recall. It only records observables from running the binder-only classifier on foreign production SQL. Published as returned - not tuned.

| field | value |
|---|---|
| project | [mozilla/bigquery-etl](https://github.com/mozilla/bigquery-etl) |
| commit | `717b6a14846a3a294049a6cab42168eaf4bb5b2c` |
| subject table | `clients_daily_v6` (aliases: clients_daily / clients_daily_v6) |
| column under change | `client_id` |
| dialect | `bigquery` |
| queries scored | 118 |

## Command

```bash
python tools/real_world_mozilla_run.py --repo /tmp/premortem-rw/bigquery-etl --out-dir docs --sha 717b6a14846a3a294049a6cab42168eaf4bb5b2c
```

Raw output: [`docs/real-world-run-raw.json`](real-world-run-raw.json)

## Correction (CLEARED precondition)

An earlier draft of this run reported CLEARED=87 alongside a table-resolution rate of 0.09. Those numbers were logically inconsistent: the binder was emitting `BOUND_ELSEWHERE` for *any* qualifier that was not the subject — including BigQuery STRUCT paths (`client_info.client_id`), UNNEST aliases, and unresolvable names. **CLEARED now requires positive resolution to a known non-subject table in the loaded schema map**; otherwise the verdict is UNKNOWN (`couldn't resolve qualifier … — not guessing`). Struct paths on the subject bind as HARD/SOFT by clause. The distribution below is from the corrected classifier. Most of the old false CLEAREDs become honest UNKNOWNs — the better story when schemas are incomplete.

## Parse rate

**84.75%** (100/118) statements produced a non-parse-failure verdict. Parse failures: **18** (typically heavy Jinja, BigQuery scripting, or sqlglot coverage gaps).

Example parse failures:

- `bigquery_etl/glam/templates/histogram_bucket_counts_v1.sql` - sqlglot parse failed: Invalid expression / Unexpected token. Line 4, Col: 4.
   __JINJA__ 
 

WITH
 __JINJA__ ,
build_ids AS (
  SELECT
    app_build_id,
    channel,
  FROM
    sampled_source
  GRO
- `sql/moz-fx-data-shared-prod/fenix_derived/attributable_clients_v1/query.sql` - sqlglot parse failed: Expecting ). Line 23, Col: 10.
  od`.fenix.baseline
  WHERE
     
      DATE(submission_timestamp) >= DATE("2021-01-01")
     
      DATE(submission_timestamp) = @submission_date
     
  GROUP BY
    submission_date,
    sample_id,
    c
- `sql/moz-fx-data-shared-prod/fenix_derived/attributable_clients_v2/query.sql` - sqlglot parse failed: Expecting ). Line 23, Col: 10.
  red-prod`.fenix.baseline
  WHERE
     
      DATE(submission_timestamp) >= "2021-08-01"
     
      DATE(submission_timestamp) = @submission_date
     
  GROUP BY
    submission_date,
    sample_id,
    c

## Verdict distribution

| verdict | count | share |
|---|---:|---:|
| hard | 1 | 0.8% |
| soft | 1 | 0.8% |
| unknown | 102 | 86.4% |
| cleared | 13 | 11.0% |
| unaffected | 1 | 0.8% |

## UNKNOWN breakdown

| reason bucket | count |
|---|---:|
| unresolvable_qualifier | 82 |
| unparseable | 18 |
| star | 2 |

## Table-resolution rate

Loaded **687** table schemas from `schema.yaml`. Among distinct tables mentioned in the scored SQL, **32** had a schema and **333** did not (resolution rate **0.0877**).

## Concrete examples

### 1. `sql/moz-fx-data-shared-prod/firefoxdotcom_derived/gclid_conversions_v1/query.sql` -> **HARD**

- evidence: `JOIN`

```sql
--Step 1: Get all combos of GCLID, GA Client ID, & Stub Session IDs Seen in Last 30 Days
WITH gclids_to_ga_ids AS (
  SELECT DISTINCT
    unnested_gclid AS gclid,
    ga_client_id,
    stub_session_id
```

### 2. `sql/moz-fx-data-shared-prod/telemetry_derived/clients_last_seen_v1/query.sql` -> **SOFT**

- evidence: `SELECT`

```sql
-- Note that this query runs in the telemetry_derived dataset, so sees derived tables
-- rather than the user-facing views (so key_value structs haven't been eliminated, etc.)
WITH _current AS (
  SEL
```

### 3. `sql/glam-fenix-dev/glam_etl/org_mozilla_fenix_glam_nightly__latest_versions_v1/query.sql` -> **CLEARED**

- evidence: `BOUND_ELSEWHERE:org_mozilla_fenix_glam_nightly__view_clients_daily_scalar_aggregates_v1`

```sql
-- query for org_mozilla_fenix_glam_nightly__latest_versions_v1;
WITH extracted AS (
  SELECT
    client_id,
    channel,
    app_version
  FROM
    `glam-fenix-dev.glam_etl.org_mozilla_fenix_glam_nig
```

### 4. `bigquery_etl/glam/templates/histogram_bucket_counts_v1.sql` -> **UNKNOWN**

- evidence: `PARSE`
- unknown_reason: sqlglot parse failed: Invalid expression / Unexpected token. Line 4, Col: 4.
   __JINJA__ 
 

[4mWITH[0m
 __JINJA__ ,
build_ids AS (
  SELECT
    app_build_id,
    channel,
  FROM
    sampled_source
  GRO

```sql
__JINJA__ 
 

WITH
 __JINJA__ ,
build_ids AS (
  SELECT
    app_build_id,
    channel,
  FROM
    sampled_source
  GROUP BY
    1,
    2
  HAVING
      COUNT(DISTINCT client_id) >  __JINJA__ 
  UNION 
```

### 5. `sql/glam-fenix-dev/glam_etl/firefox_desktop__clients_daily_histogram_aggregates_metrics_v1/query.sql` -> **UNKNOWN**

- evidence: `SELECT`
- unknown_reason: couldn't resolve qualifier `metrics_v1` — not guessing

```sql
-- Query generated by: python3 -m bigquery_etl.glam.clients_daily_histogram_aggregates --source-table firefox_desktop_stable.metrics_v1
WITH extracted AS (
  SELECT
    *,
    DATE(submission_timestam
```

## Classifier-defect flags (for Aug 3 triage)

Items below looked surprising on inspection of the raw output - possible defects rather than honest UNKNOWN. No code was changed in response.

_No automatic defect flags fired beyond the UNKNOWN/parse mass. Review the UNKNOWN unresolvable bucket and parse failures manually._

## Honesty note

Jinja templating was stripped to placeholders before sqlglot. That inflates parse failures and can distort binding for models that are only valid after dbt compilation. A compiled-manifest follow-up would be stricter; this run deliberately used the public SQL as checked in.
