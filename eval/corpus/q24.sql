SELECT o.*, c.region FROM analytics.order_history o JOIN analytics.customers c ON o.customer_id = c.customer_id
