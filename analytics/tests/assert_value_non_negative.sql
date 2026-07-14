-- Custom (singular) dbt test: fails if any cleaned reading is negative.
-- dbt tests pass when this query returns ZERO rows.

select *
from {{ ref('stg_air_quality') }}
where value < 0
