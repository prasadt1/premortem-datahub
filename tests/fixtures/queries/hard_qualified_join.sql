SELECT o.id
FROM orders o
JOIN customers c ON o.customer_id = c.id
WHERE o.order_status = 1;
