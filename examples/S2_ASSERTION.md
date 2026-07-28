# S2 assertion probe

Created for Prasad's Quickstart UI check (Data Quality tools are MCP-disabled on OSS; GraphQL path used).

- **URN:** `urn:li:assertion:3352b99f-7e64-4df3-a28f-93c3aaf0123e`
- **Dataset:** `urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.analytics.order_history,PROD)`
- **Platform:** `premortem`
- **Result reported:** FAILURE
- **Column:** `order_status` (in description/properties; `fieldPath` omitted because this Quickstart rejects `schemaField` asserteeUrn on `reportAssertionResult`)

Please open the ORDER_HISTORY dataset → Assertions / Quality and confirm whether this custom assertion renders.
