SELECT o.order_id, i.product_id FROM analytics.order_history o JOIN analytics.order_items i ON o.order_id = i.order_id WHERE order_status = 'PARTIALLY_SHIPPED'
