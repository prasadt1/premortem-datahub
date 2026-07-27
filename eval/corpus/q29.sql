SELECT o.order_id, s.shipment_id FROM analytics.order_history o JOIN logistics.shipments s ON o.order_id = s.order_id ORDER BY order_status
