# MCP composition (filming)

Register **both** servers so the tool-call log shows DataHub MCP for catalog
context and Premortem MCP for rehearsal. That split is the composition beat.

Set `DATAHUB_TELEMETRY_ENABLED=false` or `track.datahubproject.io` timeout
retries scroll through the session on camera.

Verified against Quickstart **v1.5.0.6**: DataHub MCP logs
`is_oss=True`, **Mutation Tools ENABLED**, Data Quality Tools DISABLED;
Premortem exposes `rehearse_schema_change` / `explain_finding` /
`write_back_forecast`. A dual-stdio session confirmed DataHub
`list_schema_fields` + Premortem `rehearse_schema_change` (baseline 3,
`write_payload` with assertion / tag / description).

## Config (Claude Code / Cursor)

```json
{
  "mcpServers": {
    "datahub": {
      "command": "uvx",
      "args": ["mcp-server-datahub@latest"],
      "env": {
        "DATAHUB_GMS_URL": "http://localhost:8080",
        "DATAHUB_TELEMETRY_ENABLED": "false",
        "TOOLS_IS_MUTATION_ENABLED": "true"
      }
    },
    "premortem": {
      "command": "/path/to/Premortem/.venv/bin/premortem-mcp",
      "env": {
        "DATAHUB_GMS_URL": "http://localhost:8080",
        "DATAHUB_TELEMETRY_ENABLED": "false",
        "PREMORTEM_CATALOG": "kit"
      }
    }
  }
}
```

Install Premortem MCP once:

```bash
cd /path/to/Premortem
source .venv/bin/activate
pip install -e ".[datahub,mcp]"
```

## On-camera prompt

Ask in plain language to rehearse renaming `order_status` → `order_state` on
the demo ORDER_HISTORY dataset. Expect:

1. DataHub MCP for context (`search` / `list_schema_fields` / `get_lineage` /
   `get_dataset_queries`)
2. Premortem `rehearse_schema_change` — the only Premortem tool on camera;
   returns the forecast plus `write_payload`
3. Host applies `write_payload` **as-is** via DataHub mutation tools
   (`add_tags`, `update_description`) and GraphQL `upsertCustomAssertion`
   (Data Quality tools are DISABLED on OSS MCP — see
   [OSS_ISSUES.md](OSS_ISSUES.md) #2)

Do not recompute severities, paraphrase the markdown, or invent tags.

## Catalog backend

- Default: **Kit** (`datahub-agent-context`) — stage-1 surface for `--live`
- Fallback: `PREMORTEM_CATALOG=graphql` or `premortem --live --catalog graphql`
