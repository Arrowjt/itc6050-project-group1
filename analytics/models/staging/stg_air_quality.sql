-- stg_air_quality.sql
--
-- Cleans the raw OpenAQ chain (measurements_daily -> sensors -> locations) into
-- one row per (sensor, day) reading, in a single standard unit (µg/m³).
--
-- Note: measurements_daily is already OpenAQ's own daily aggregate (value_avg/
-- value_max/etc, one row per sensor per day) -- it is NOT raw hourly data. The
-- "daily average" work happens one level up, in city_daily_avg.sql, which
-- averages across every sensor/station within the same capital.
--
-- Cleaning rules applied here:
--   1. Drop impossible readings (negative average)
--   2. Convert mixed units (ppm/ppb) to µg/m³ using each gas's molecular weight:
--      µg/m³ = ppm * MW * 1000 / 24.45   (or ppb * MW / 24.45)
--      PM2.5/PM10 are mass-based already, so no conversion applies to them.
--   3. Drop days below 75% hourly completeness (WHO/EPA standard) -- percent_complete
--      is stored 0-100 in this data, confirmed from raw rows.
--   4. Restrict to the target pollutant set: pm25, no2, co, o3, so2
--      (confirmed via `select distinct parameter_name, parameter_units from
--      raw.measurements_daily` -- these 5 codes exist exactly as named, mixed
--      across ppb/ppm/µg/m³ for the gases, µg/m³-only for pm25)
--   5. Drop rows with no city (i.e. sensor/location join failed)

with measurements as (

    select
        sensor_id,
        date_utc,
        value_avg,
        value_max,
        lower(parameter_name)  as parameter,
        lower(parameter_units) as unit,
        expected_count,
        observed_count,
        percent_complete
    from {{ source('raw', 'measurements_daily') }}
    where value_avg is not null

),

sensors as (

    select
        sensor_id,
        location_id
    from {{ source('raw', 'sensors') }}

),

locations as (

    select
        location_id,
        capital_name as city,      -- the capital this station is scoped to
        country_name as country,
        capital_cca2
    from {{ source('raw', 'locations') }}

),

molecular_weights as (

    select * from {{ ref('pollutant_molecular_weights') }}

),

joined as (

    select
        m.sensor_id,
        m.date_utc,
        m.value_avg,
        m.value_max,
        m.unit,
        m.parameter,
        m.percent_complete,
        l.city,
        l.country,
        mw.molecular_weight_g_per_mol
    from measurements m
    inner join sensors s            on m.sensor_id = s.sensor_id
    inner join locations l          on s.location_id = l.location_id
    left join molecular_weights mw  on m.parameter = mw.parameter

),

cleaned as (

    select
        -- surrogate key: one reading = one sensor + one day
        md5(cast(sensor_id as varchar) || '-' || cast(date_utc as varchar)) as measurement_id,
        city,
        country,
        parameter,
        case
            when unit = 'ppm' then value_avg * molecular_weight_g_per_mol * 1000 / 24.45
            when unit = 'ppb' then value_avg * molecular_weight_g_per_mol / 24.45
            else value_avg
        end as value,
        case
            when unit = 'ppm' then value_max * molecular_weight_g_per_mol * 1000 / 24.45
            when unit = 'ppb' then value_max * molecular_weight_g_per_mol / 24.45
            else value_max
        end as max_value,
        'ug/m3' as unit,
        date_utc,
        percent_complete
    from joined
    where
        value_avg >= 0
        and percent_complete >= 75
        and parameter in ('pm25', 'no2', 'co', 'o3', 'so2')
        and city is not null

)

select * from cleaned
