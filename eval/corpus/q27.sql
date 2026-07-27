SELECT c.customer_id, (SELECT MAX(o.created_at) FROM analytics.order_history o WHERE o.customer_id = c.customer_id AND o.order_status = 'COMPLETE') AS last_completed_at FROM analytics.customers c
