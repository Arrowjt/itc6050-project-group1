-- city_daily_avg.sql
--
-- Mart: one row per city + pollutant + day.
-- Since a capital can have multiple monitoring stations, this averages
-- stg_air_quality's per-sensor daily value across all sensors/stations in
-- that city, and takes the max across them too.
-- This is what the Streamlit dashboard will query directly.

with stg as (

    select * from {{ ref('stg_air_quality') }}

)

select
    city,
    country,
    parameter,
    date_utc::date as reading_date,
    avg(value)      as avg_value,
    max(max_value)  as max_value,
    count(*)        as num_readings
from stg
group by
    city,
    country,
    parameter,
    date_utc::date
