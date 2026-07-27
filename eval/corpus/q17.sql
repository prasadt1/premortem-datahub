SELECT order_status, s.carrier FROM analytics.order_history o JOIN logistics.shipments s ON o.order_id = s.order_id
