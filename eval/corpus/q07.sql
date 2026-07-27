WITH base AS (SELECT order_id, order_status FROM analytics.order_history) SELECT order_id, order_status FROM base
