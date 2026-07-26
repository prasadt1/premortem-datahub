Schema rehearsal: drop order_status

Impact Analysis baseline: 1 downstream dependents

HARD (8)
- emitter_hard_where — [WHERE] SELECT order_id FROM order_history WHERE order_status = 'COMPLETE'
- emitter_unknown_bare — [WHERE] SELECT o.order_id FROM order_history o JOIN customers c ON o.customer_id = c.customer_id WHERE order_status = 'OPEN' — agent: bound `order_status` to subject schema (fields include column; clause=WHERE); treat as HARD pending human confirm
- hard_qualified — [WHERE] SELECT o.order_id FROM order_history o JOIN customers c ON o.customer_id = c.customer_id WHERE o.order_status = 'OPEN'
- hard_qualified_join — [WHERE] SELECT o.order_id FROM order_history o JOIN customers c ON o.customer_id = c.customer_id WHERE o.order_status = 'OPEN'
- hard_where_order_status — [WHERE] SELECT order_id, customer_id FROM order_history WHERE order_status = 'COMPLETE'
- hard_where_order_status — [WHERE] SELECT order_id, customer_id FROM order_history WHERE order_status = 'COMPLETE'
- unknown_bare_join — [WHERE] SELECT o.order_id, c.customer_id FROM order_history o JOIN customers c ON o.customer_id = c.customer_id WHERE order_stat — agent: bound `order_status` to subject schema (fields include column; clause=WHERE); treat as HARD pending human confirm
- unknown_bare_join — [WHERE] SELECT o.order_id, c.customer_id FROM order_history o JOIN customers c ON o.customer_id = c.customer_id WHERE order_stat — agent: bound `order_status` to subject schema (fields include column; clause=WHERE); treat as HARD pending human confirm

SOFT (3)
- emitter_soft_select — [SELECT] SELECT order_status, order_id FROM order_history
- soft_select_order_status — [SELECT] SELECT order_status, order_id, order_total FROM order_history
- soft_select_order_status — [SELECT] SELECT order_status, order_id, order_total FROM order_history

UNKNOWN / needs human (0)
- (none)

UNAFFECTED / no query evidence: 2
