SELECT c.customer_id, c.customer_name FROM analytics.customers c WHERE c.customer_id IN (SELECT customer_id FROM analytics.order_history WHERE order_status = 'ON_HOLD')
