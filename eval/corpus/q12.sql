SELECT order_status, COUNT(*) AS n FROM analytics.order_history GROUP BY order_status
