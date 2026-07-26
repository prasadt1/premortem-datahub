Schema rehearsal: order_status → rename to order_state

Impact Analysis baseline: 12 downstream dependents

HARD (4)
- hard_groupby — [GROUP] SELECT id, COUNT(*) AS n
FROM orders
GROUP BY order_status;
- hard_orderby — [ORDER] SELECT id
FROM orders
ORDER BY order_status;
- hard_qualified_join — [WHERE] SELECT o.id
FROM orders o
JOIN customers c ON o.customer_id = c.id
WHERE o.order_status = 1;
- hard_where — [WHERE] SELECT id FROM orders WHERE order_status = 1;

SOFT (1)
- soft_select — [SELECT] SELECT order_status, id FROM orders;

UNKNOWN / needs human (1)
- unknown_bare_join — [WHERE] SELECT o.id
FROM orders o
JOIN customers c ON o.customer_id = c.id
WHERE order_status = 1; — unqualified `order_status` with 2 tables in scope; needs human/agent

UNAFFECTED / no query evidence: 1
