SELECT t.ticket_id FROM support.tickets t WHERE t.priority IN (SELECT order_status FROM analytics.order_history)
