{{ config(materialized='table') }}
SELECT order_id, order_status FROM {{ source('analytics','order_history') }}
