SELECT order_id, CASE WHEN order_status = 'COMPLETE' THEN 'done' ELSE 'wip' END AS phase FROM analytics.order_history
