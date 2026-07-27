SELECT o.order_id, s.carrier FROM analytics.order_history o JOIN logistics.shipments s ON o.order_id = s.order_id AND o.order_status = 'SHIPPED'
