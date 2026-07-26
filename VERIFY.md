# Premortem — human verification checklist

Cursor will not claim write-back or wire catalog mutations until Gate 1 is checked.

## Gate 1 — DataHub write-back (highest blast radius)

- [ ] Path: OSS Quickstart + self-hosted `mcp-server-datahub` **or** DataHub Cloud MCP
- [ ] Mutation works: `add_tags` / `update_description` / `save_document` (or GraphQL) visible in UI
- [ ] Result: **PASS** → keep write-back demo · **FAIL** → cut write-back claims; forecast + frozen eval only

Notes:

```
date:
path:
tool that worked:
```

## Gate 2 — Query history

- [ ] `datahub datapack load showcase-ecommerce`
- [ ] `get_dataset_queries` returns SQL for demo URN
- [ ] Demo URN + column locked in `examples/DEMO.md`

## Gate 3 — Exec counts

- [ ] Count field present on query payload → `RANK_BY_EXEC_COUNT=true`
- [ ] Else → never print `(exec×N)`

## Gate 4 — Cockroach / AWS (parallel, today)

- [ ] Bedrock: region + model requested (queues)
- [ ] `CREATE VECTOR INDEX` on scratch table (note exact error/flag)
- [ ] `SHOW ZONE CONFIGURATION` → real `gc.ttlseconds`
- [ ] If Managed MCP writes needed later: consent scopes noted

When Gates 1–3 are filled, ping Claude for frozen-eval design + Cursor for MCP integration.
