-- who_pm25_alerts.sql
--
-- Every city-day where average PM2.5 exceeded the WHO safe-air threshold
-- (25 µg/m³). This is the dashboard's required "alert table" component,
-- pre-built so the dashboard just SELECTs from here directly.

{{ config(materialized='view') }}

select
    city,
    country,
    reading_date,
    avg_value as pm25_avg_value
from {{ ref('city_daily_avg') }}
where parameter = 'pm25'
  and avg_value > 25
order by avg_value desc