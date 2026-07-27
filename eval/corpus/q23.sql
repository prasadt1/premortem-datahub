SELECT customer_id, COUNT(*) AS n FROM analytics.order_history GROUP BY customer_id HAVING COUNT(CASE WHEN order_status = 'CANCELLED' THEN 1 END) > 3
