Schema rehearsal: drop order_status

Impact Analysis baseline: 0 downstream dependents

HARD (3)
- emitter_hard_where — [WHERE] SELECT order_id FROM order_history WHERE order_status = 'COMPLETE'
- hard_qualified_join — [WHERE] SELECT o.order_id FROM order_history o JOIN customers c ON o.customer_id = c.customer_id WHERE o.order_status = 'OPEN'
- hard_where_order_status — [WHERE] SELECT order_id, customer_id FROM order_history WHERE order_status = 'COMPLETE'

SOFT (2)
- emitter_soft_select — [SELECT] SELECT order_status, order_id FROM order_history
- soft_select_order_status — [SELECT] SELECT order_status, order_id, order_total FROM order_history

UNKNOWN / needs human (2)
- emitter_unknown_bare — [WHERE] SELECT o.order_id FROM order_history o JOIN customers c ON o.customer_id = c.customer_id WHERE order_status = 'OPEN' — unqualified `order_status` with 2 tables in scope; needs human/agent
- unknown_bare_join — [WHERE] SELECT o.order_id, c.customer_id FROM order_history o JOIN customers c ON o.customer_id = c.customer_id WHERE order_stat — unqualified `order_status` with 2 tables in scope; needs human/agent

UNAFFECTED / no query evidence: 1
