SELECT order_id FROM analytics.order_history WHERE order_status = :status_param AND currency = ${currency_code}
