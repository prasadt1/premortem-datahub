SELECT order_id, ROW_NUMBER() OVER (PARTITION BY order_status ORDER BY created_at DESC) AS rn FROM analytics.order_history QUALIFY rn = 1
