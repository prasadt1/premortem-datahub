Schema rehearsal: order_status → rename to order_state

Impact Analysis baseline: 1 downstream dependents

HARD (3)
- decoy_shipments_order_status — [WHERE] SELECT s.shipment_id FROM shipments s WHERE s.order_status = 'SHIPPED'
- hard_qualified_join — [WHERE] SELECT o.order_id FROM order_history o JOIN customers c ON o.customer_id = c.customer_id WHERE o.order_status = 'OPEN'
- hard_where_order_status — [WHERE] SELECT order_id, customer_id FROM order_history WHERE order_status = 'COMPLETE'

SOFT (1)
- soft_select_order_status — [SELECT] SELECT order_status, order_id, order_total FROM order_history

UNKNOWN / needs human (1)
- unknown_bare_two_tables — [WHERE] SELECT o.order_id, s.shipment_id FROM order_history o JOIN shipments s ON o.order_id = s.order_id WHERE order_status = ' — unqualified `order_status` with 2 tables in scope; needs human/agent

UNAFFECTED / no query evidence: 2
