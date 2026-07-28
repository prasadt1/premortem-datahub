Schema rehearsal: drop order_status

Impact Analysis baseline: 3 downstream dependents

HARD (5)
- emitter_hard_where — [WHERE] SELECT order_id FROM order_history WHERE order_status = 'COMPLETE'
- emitter_unknown_bare — [WHERE] SELECT o.order_id FROM order_history o JOIN customers c ON o.customer_id = c.customer_id WHERE order_status = 'OPEN'
- hard_qualified_join — [WHERE] SELECT o.order_id FROM order_history o JOIN customers c ON o.customer_id = c.customer_id WHERE o.order_status = 'OPEN'
- hard_where_order_status — [WHERE] SELECT order_id, customer_id FROM order_history WHERE order_status = 'COMPLETE'
- unknown_bare_join — [WHERE] SELECT o.order_id, c.customer_id FROM order_history o JOIN customers c ON o.customer_id = c.customer_id WHERE order_stat

SOFT (2)
- emitter_soft_select — [SELECT] SELECT order_status, order_id FROM order_history
- soft_select_order_status — [SELECT] SELECT order_status, order_id, order_total FROM order_history

UNKNOWN / needs human (1)
- unknown_bare_two_tables — [WHERE] SELECT o.order_id FROM order_history o JOIN shipments s ON o.order_id = s.order_id WHERE order_status = 'OPEN' — unqualified `order_status` with 2 tables in scope; needs human/agent

CLEARED (references a same-named column that binds elsewhere) (1)
- decoy_shipments_order_status — binds to `shipments` — SELECT s.shipment_id FROM shipments s WHERE s.order_status = 'SHIPPED'

No query evidence of `order_status` on subject: 1
