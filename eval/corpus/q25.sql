WITH o AS (SELECT * FROM analytics.order_history) SELECT order_id FROM o WHERE order_status = 'OPEN'
