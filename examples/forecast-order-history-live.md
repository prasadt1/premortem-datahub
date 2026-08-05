Schema rehearsal: order_status → rename to order_state

Impact Analysis baseline: 3 downstream dependents

HARD (5)
- emitter_hard_where — [WHERE] `SELECT order_id FROM order_history WHERE order_status = 'COMPLETE'`
- emitter_unknown_bare — [WHERE] `SELECT o.order_id FROM order_history o JOIN customers c ON o.customer_id = c.customer_id WHERE order_status = 'OPEN'`
- hard_qualified_join — [WHERE] `SELECT o.order_id FROM order_history o JOIN customers c ON o.customer_id = c.customer_id WHERE o.order_status = 'OPEN'`
- hard_where_order_status — [WHERE] `SELECT order_id, customer_id FROM order_history WHERE order_status = 'COMPLETE'`
- unknown_bare_join — [WHERE] `SELECT o.order_id, c.customer_id FROM order_history o JOIN customers c ON o.customer_id = c.customer_id WHERE order_stat`

SOFT (2)
- emitter_soft_select — [SELECT] `SELECT order_status, order_id FROM order_history`
- soft_select_order_status — [SELECT] `SELECT order_status, order_id, order_total FROM order_history`

UNKNOWN / needs human (1)
- unknown_bare_two_tables — [WHERE] `SELECT o.order_id FROM order_history o JOIN shipments s ON o.order_id = s.order_id WHERE order_status = 'OPEN'` — unqualified order_status with 2 tables in scope; needs human/agent

CLEARED (references a same-named column that binds elsewhere) (1)
- decoy_shipments_order_status — binds to `shipments` — `SELECT s.shipment_id FROM shipments s WHERE s.order_status = 'SHIPPED'`

Notify (who to warn before Friday)
HARD priority
- `urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.analytics.order_details,PROD)` (downstream) → b2fd91.1e0398a3-113f-475e-b6fc-32ab72a634d2 (`urn:li:corpGroup:b2fd91.1e0398a3-113f-475e-b6fc-32ab72a634d2`), b2fd91.brock1@example.com (`urn:li:corpuser:b2fd91.brock1@example.com`), b2fd91.jonny1@example.com (`urn:li:corpuser:b2fd91.jonny1@example.com`)

no owners recorded
- `urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.analytics.order_history,PROD)` (subject, worst=hard)
- `urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.analytics.shipments,PROD)` (downstream, worst=hard)
- `urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.analytics.order_details_replica,PROD)` (downstream, worst=hard)

No query evidence of `order_status` on subject: 1
