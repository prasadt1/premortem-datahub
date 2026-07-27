SELECT order_id FROM analytics.order_history WHERE CASE WHEN order_status IN ('OPEN', 'ON_HOLD') THEN 1 ELSE 0 END = 1
