-- city_pollution_ranking.sql
--
-- Every city ranked by its overall average value, per pollutant -- most
-- polluted first. The dashboard's "top 10 most polluted cities (avg PM2.5)"
-- bar chart is just `WHERE parameter = 'pm25' ... LIMIT 10` against this.


{{ config(materialized='view') }}

select
    city,
    country,
    parameter,
    avg(avg_value) as overall_avg_value,
    max(max_value) as overall_max_value,
    rank() over (partition by parameter order by avg(avg_value) desc) as pollution_rank
from {{ ref('city_daily_avg') }}
group by city, country, parameter