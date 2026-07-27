-- TODO: re-add order_status filter after backfill
SELECT order_id, order_total FROM analytics.order_history WHERE created_at > '2026-01-01'
