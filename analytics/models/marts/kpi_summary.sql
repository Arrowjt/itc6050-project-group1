-- kpi_summary.sql
--
-- One row with the numbers for the dashboard's KPI row:
-- cities monitored, total readings loaded, and the date range covered.
-- Convenience view on top of city_daily_avg -- not required by the brief,
-- built so the dashboard doesn't need to write its own aggregation SQL.

{{ config(materialized='view') }}

select
    count(distinct city) as cities_monitored,
    sum(num_readings)    as total_readings,
    min(reading_date)    as earliest_date,
    max(reading_date)    as latest_date
from {{ ref('city_daily_avg') }}