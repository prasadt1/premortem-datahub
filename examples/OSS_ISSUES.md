# OSS Quickstart limitations (accumulated)

Tracked against DataHub Quickstart **v1.5.0.6** during the Premortem hackathon
build. Client context where relevant: `mcp-server-datahub` **0.6.0**,
`sqlglot` **30.13.0**.

Filed upstream (bonus: meaningful contributions from real integration work):

1. **`listQueries` / QUERY search empty until seeded + indexed** —
   [datahub-project/datahub#18676](https://github.com/datahub-project/datahub/issues/18676).
   Not permanently empty on v1.5.0.6 — after GraphQL `createQuery` + a short
   index wait, Kit/`get_dataset_queries` populated. Seed file remains a fallback.

2. **Data Quality tools DISABLED on DataHub MCP (OSS)** —
   [acryldata/mcp-server-datahub#151](https://github.com/acryldata/mcp-server-datahub/issues/151).
   Startup logs `is_oss=True`, Mutation Tools ENABLED (with
   `TOOLS_IS_MUTATION_ENABLED=true`), Data Quality Tools DISABLED. Custom
   assertion upsert/report stay on GraphQL; tag/description mutations via MCP
   work.

3. **Document entities create successfully but often never appear in Quickstart search** —
   [datahub-project/datahub#18675](https://github.com/datahub-project/datahub/issues/18675).
   Write-back hero is assertion + tag + description instead.

4. **`assertionRunEvent` rejects `schemaField` asserteeUrn** —
   [datahub-project/datahub#18674](https://github.com/datahub-project/datahub/issues/18674).
   When `upsertCustomAssertion` sets `fieldPath`, `reportAssertionResult` fails
   validation (`Required: [dataset]` on `/asserteeUrn`). Premortem assertions are
   **dataset-scoped** with the column named in the description/properties.
   Strongest of the four; clearest repro.
