SELECT order_id FROM analytics.order_history WHERE order_state <> 'CANCELLED' AND order_total > 500
