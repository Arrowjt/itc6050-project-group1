# Raw Data Quality Notes — `raw.measurements_daily`

Findings from the initial ingestion (7.08M daily rows, 85 capitals, 2016–2026, OpenAQ v3 `/days` endpoint). These are the issues Track B's staging model needs to handle before aggregation. Each is backed by a query you can re-run to see the current numbers.

## Summary of what needs cleaning

| Issue | Scale | Staging action |
|---|---|---|
| Mixed units per pollutant | see below — the big one | Convert all gases to µg/m³ before aggregating |
| Below 75% daily completeness | ~1.40M rows (~20%) | Filter `percent_complete >= 75` |
| Null values | ~72K rows (~1%) | Filter `value_avg IS NOT NULL` |
| Negative values | ~6.1K rows | Filter `value_avg >= 0` |
| Sensor over-range ceiling (exactly 10000) | ~360 core rows | Cap/filter as outliers |
| Non-target parameters | temperature, humidity, um003, wind, bc, pm1, no, nox | Filter to the 6 target pollutants |

Target pollutants for the project: **pm25, pm10, no2, o3, so2, co**.

## 1. Mixed units — the critical one

The same gas is reported in different units by different countries/providers. You **cannot average `value_avg` across sensors without converting to a common unit first** — a CO reading of 5 ppm and 5 µg/m³ are physically different quantities. This is why raw CO shows a max of 2,740,000 (a ppb value sitting next to µg/m³ values).

Observed units per pollutant:

- **CO**: µg/m³ (263K), ppm (244K), ppb (29K)
- **NO2**: µg/m³ (975K), ppm (400K), ppb (29K)
- **SO2**: µg/m³ (330K), ppm (251K), ppb (24K)
- **O3**: µg/m³ (600K), ppm (213K)
- **NO / NOx**: mixed ppm / µg/m³ / ppb (not target pollutants, but same issue)
- **Temperature**: Celsius (184K), Fahrenheit (1.6K) — not a target pollutant
- **Particulates (PM2.5, PM10, PM1)**: µg/m³ only — **no conversion needed**

So: particulates are clean; **the four target gases (CO, NO2, SO2, O3) need unit normalization.**

### Conversion reference (ppb/ppm → µg/m³)

Standard conversion at 25°C and 1 atm:

```
µg/m³ = ppb × (molecular_weight / 24.45)
1 ppm = 1000 ppb
```

Molecular weights (g/mol) for the target gases:

| Gas | Molecular weight |
|---|---|
| NO2 | 46.01 |
| SO2 | 64.07 |
| CO  | 28.01 |
| O3  | 48.00 |

Example: 40 ppb NO2 = 40 × (46.01 / 24.45) ≈ 75.3 µg/m³.

Note the 24.45 molar volume assumes 25°C/1 atm. Real conditions vary, so this is an approximation — acceptable and standard for a monitoring dashboard, but worth stating as a limitation in the report.

Query to see the unit split yourself:
```sql
SELECT parameter_name, parameter_units, COUNT(*) AS rows
FROM raw.measurements_daily
GROUP BY parameter_name, parameter_units
ORDER BY parameter_name, rows DESC;
```

## 2. Data completeness (75% rule)

~1.40M rows (~20%) have `percent_complete < 75`, meaning fewer than ~18 of 24 hours contributed to that daily average. Per the US EPA 40 CFR Part 50 App. N and EEA standards, these should be excluded from valid daily aggregates.

The raw table carries `percent_complete`, `expected_count`, and `observed_count` straight from the OpenAQ `/days` endpoint, so the filter is direct:
```sql
WHERE percent_complete >= 75
```

## 3. Nulls and negatives

- **Nulls**: ~72K rows where `value_avg IS NULL`. Filter out.
- **Negatives**: ~6.1K rows with `value_avg < 0` (impossible concentrations — sensor/calibration errors). The brief explicitly requires a custom test for this. Filter `value_avg >= 0`.

## 4. Sensor over-range ceiling

Several pollutants show a spike of readings at exactly `value_avg = 10000` (pm25: 75, pm10: 66, co: 63, no2: 54, so2: 52, o3: 51). This is a sensor saturation/over-range placeholder, not a real concentration. Recommend capping or filtering these as outliers. Consider also an upper physical bound per pollutant (e.g. PM2.5 rarely exceeds ~1000 µg/m³ even in extreme events).

## 5. Non-target parameters

The raw table includes parameters beyond the 6 targets: `temperature`, `relativehumidity`, `um003`, `pm1`, `no`, `nox`, `wind_speed`, `wind_direction`, `bc`. Staging should filter to the target set unless a stretch goal (e.g. weather correlation) needs them.

## Suggested staging → mart flow

Based on the aggregation research (WHO / EPA / EEA methodology):

1. **stg_measurements**: filter to target pollutants; drop nulls, negatives, and `percent_complete < 75`; convert gases to µg/m³; cap over-range outliers; cast `date_utc` to a true date.
2. **int_station_daily** (optional intermediate): one clean row per sensor per day (mostly already at this grain from the `/days` endpoint).
3. **city_daily**: average across a city's sensors → `city × parameter × date`; keep a `station_count` and a confidence flag (low if ≤2 stations); join `raw.countries` for region/subregion.
4. **WHO comparison**: flag `exceeds_who_24h` / `exceeds_who_annual`. Note O3's WHO guideline is defined on the daily max 8-hour mean, not a 24-hour mean — the `/days` average is not directly comparable, so treat O3 comparisons with a caveat.

## Note on historical depth

The `/days` endpoint returned each sensor's **full history (2016–2026)**, not the 2-year window requested via `datetime_from`. We retained the full depth in the raw layer; window to a shorter period in staging if needed (`WHERE date_utc >= '2024-01-01'`). Full DB size is ~3.35 GB (measurements ~1.66 GB).
