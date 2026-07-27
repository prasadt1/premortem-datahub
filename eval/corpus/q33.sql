SELECT c.customer_id FROM analytics.customers c WHERE EXISTS (SELECT 1 FROM analytics.order_history o WHERE o.customer_id = c.customer_id AND o.order_status = 'OPEN')
