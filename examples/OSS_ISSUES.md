# OSS Quickstart limitations (accumulated)

Tracked against DataHub Quickstart **v1.5.0.6** during the Premortem hackathon build.

1. **`listQueries` / QUERY search staleness** — historically empty until seeded + indexed; now works, but seed file remains a fallback.
2. **Data Quality tools DISABLED on DataHub MCP (OSS)** — assertions are GraphQL-only; not exposed via MCP mutation tools on this stack.
3. **Document entities often not indexed** — `createDocument` may succeed without UI search visibility; write-back hero is assertion + tag + description.
4. **`assertionRunEvent` rejects `schemaField` asserteeUrn** — when `upsertCustomAssertion` sets `fieldPath`, reporting a result fails validation (`Required: [dataset]`). Premortem assertions are **dataset-scoped** with the column named in the description/properties. Strongest of the four; worth an upstream OSS issue.
