SELECT o.order_id, s.order_status FROM analytics.order_history o JOIN logistics.shipments s ON o.order_id = s.order_id WHERE s.order_status = 'RETURNED'
