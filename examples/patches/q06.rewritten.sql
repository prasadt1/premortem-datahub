SELECT o.order_id, s.carrier FROM analytics.order_history AS o JOIN logistics.shipments AS s ON o.order_id = s.order_id AND o.order_state = 'SHIPPED'
