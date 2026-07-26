SELECT id, COUNT(*) AS n
FROM orders
GROUP BY order_status;
