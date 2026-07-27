SELECT {{ dbt_utils.star(ref('order_history')) }} FROM {{ ref('order_history') }} WHERE order_status = 'OPEN'
