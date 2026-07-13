# Raw Data Quality Notes — `raw` schema

Findings from the OpenAQ v3 ingestion. These are the issues Track B's staging model needs to handle before aggregation. Each is backed by a query you can re-run to see current numbers.

**Current dataset:** 113 capitals · 2,062 locations · 9,115 sensors · 6,599,839 daily measurements · 2016–2026.

## Summary of what needs cleaning

| Issue | Scale | Where it's handled |
|---|---|---|
| Cross-border station attribution | 92 locations / 485K rows | **Fixed in ingestion** — see section 1 |
| Mixed units per pollutant | the big one — see section 2 | Staging: convert all gases to µg/m³ before aggregating |
| Below 75% daily completeness | ~20% of rows | Staging: filter `percent_complete >= 75` |
| Null values | ~1% of rows | Staging: filter `value_avg IS NOT NULL` |
| Negative values | ~6K rows | Staging: filter `value_avg >= 0` |
| Sensor over-range ceiling (exactly 10000) | ~360 core rows | Staging: cap/filter as outliers |
| Non-target parameters | temperature, humidity, um003, wind, bc, pm1, no, nox | Staging: filter to the 6 target pollutants |

Target pollutants: **pm25, pm10, no2, o3, so2, co**.

## 1. Cross-border station attribution — FIXED in ingestion

**The problem.** Stations are matched to capitals geographically: we draw a ~33 km bounding box around each capital's coordinates (from REST Countries) and take every OpenAQ station inside it. Boxes don't know about national borders, so a capital near a border — or a microstate entirely inside another country — picks up stations that belong to the neighbouring country. For example, all 18 stations inside the Vatican City box were physically in Rome, Italy.

**The naming trap.** Comparing `capital_country` to `country_name` suggested a 13.1% mismatch rate, but ~90% of those were just the two APIs using different names for the same country — "South Korea" vs "Republic of Korea", "Czechia" vs "Czech Republic", "Gambia" vs "The Gambia". **Always compare the ISO alpha-2 codes (`capital_cca2` vs `country_code`), never the names.** Doing so cut the genuine mismatch rate from 13.1% to ~4%.

**The fix.** The ingestion now only keeps a station if its OpenAQ ISO country code matches the capital's ISO country code:

```python
active = [
    r for r in results
    if _is_active(...)
    and (r.get("country") or {}).get("code") == cap["cca2"]
]
```

This removed 92 locations, 405 sensors, and 484,578 measurements.

**Consequence — 9 capitals dropped** (they had no domestic monitoring stations at all):

- *Microstates:* Vatican City, Monaco, Vaduz (Liechtenstein) — all their stations were in Italy / France / Switzerland / Austria.
- *Overseas territories:* Saint-Denis (Réunion), Fort-de-France (Martinique), Basse-Terre (Guadeloupe), Cayenne (French Guiana), Longyearbyen (Svalbard) — OpenAQ codes these by sovereign state (FR / NO), so the code check excludes them even though the stations are physically in the territory. A known, accepted limitation of the rule.
- *Cross-border:* Brazzaville — all 6 of its stations were across the Congo River in Kinshasa (the two capitals are ~5 km apart, so their boxes heavily overlapped).

Capitals near borders that **survived** kept their domestic stations and lost only the foreign ones: Gibraltar (18 Spanish stations dropped, 5 domestic kept), Bratislava (2 dropped), Luxembourg (3 dropped), Andorra la Vella (1 dropped), San Marino, Vientiane (5 Thai stations dropped).

**Verify it's clean:**
```sql
SELECT COUNT(*) FROM raw.locations
WHERE capital_cca2 IS DISTINCT FROM country_code;   -- should be 0
```

## 2. Mixed units — the critical one for Track B

The same gas is reported in different units by different countries/providers. You **cannot average `value_avg` across sensors without converting to a common unit first** — 5 ppm and 5 µg/m³ of CO are physically different quantities. This is why raw CO showed a max of 2,740,000.

Observed units per pollutant:

- **CO** — µg/m³, ppm, ppb
- **NO2** — µg/m³, ppm, ppb
- **SO2** — µg/m³, ppm, ppb
- **O3** — µg/m³, ppm
- **Particulates (PM2.5, PM10, PM1)** — µg/m³ only, **no conversion needed**

So: particulates are clean; **the four target gases (CO, NO2, SO2, O3) need unit normalisation.**

### Conversion reference (ppb/ppm → µg/m³)

At 25 °C and 1 atm:

```
µg/m³ = ppb × (molecular_weight / 24.45)
1 ppm = 1000 ppb
```

| Gas | Molecular weight (g/mol) |
|---|---|
| NO2 | 46.01 |
| SO2 | 64.07 |
| CO  | 28.01 |
| O3  | 48.00 |

Example: 40 ppb NO2 = 40 × (46.01 / 24.45) ≈ 75.3 µg/m³.

The 24.45 molar volume assumes 25 °C / 1 atm. Real conditions vary, so this is an approximation — standard and acceptable for a monitoring dashboard, but worth stating as a limitation in the report.

See the unit split yourself:
```sql
SELECT parameter_name, parameter_units, COUNT(*) AS rows
FROM raw.measurements_daily
GROUP BY parameter_name, parameter_units
ORDER BY parameter_name, rows DESC;
```

## 3. Data completeness (the 75% rule)

About 20% of rows have `percent_complete < 75`, meaning fewer than ~18 of the 24 hours contributed to that daily average. Per US EPA 40 CFR Part 50 App. N and EEA standards, these should be excluded from valid daily aggregates.

The table carries `percent_complete`, `expected_count`, and `observed_count` straight from the OpenAQ `/days` endpoint, so the filter is direct:

```sql
WHERE percent_complete >= 75
```

## 4. Nulls, negatives, and over-range values

- **Nulls** — ~1% of rows have `value_avg IS NULL`. Filter out.
- **Negatives** — ~6,000 rows with `value_avg < 0` (impossible concentrations; sensor or calibration errors). The brief explicitly requires a custom test for this. Filter `value_avg >= 0`.
- **Over-range ceiling** — several pollutants show a cluster of readings at exactly `value_avg = 10000` (pm25, pm10, co, no2, so2, o3 — roughly 50–75 each). This is a sensor saturation placeholder, not a real concentration. Cap or filter as outliers, and consider a physical upper bound per pollutant.

## 5. Non-target parameters

The table includes parameters beyond the six targets: `temperature`, `relativehumidity`, `um003`, `pm1`, `no`, `nox`, `wind_speed`, `wind_direction`, `bc`. Staging should filter to the target set unless a stretch goal needs them.

## Suggested staging → mart flow

Based on WHO / EPA / EEA methodology:

1. **stg_measurements** — filter to target pollutants; drop nulls, negatives, and `percent_complete < 75`; convert gases to µg/m³; cap over-range outliers; cast `date_utc` to a true date.
2. **city_daily** — average across a city's sensors → grain `city × parameter × date`. Keep a `station_count` and a confidence flag (low if ≤ 2 stations). Join `raw.countries` for region / subregion.
3. **WHO comparison** — flag `exceeds_who_24h` / `exceeds_who_annual`. Note O3's WHO guideline is defined on the daily max 8-hour mean, not a 24-hour mean, so the `/days` average is not directly comparable — treat O3 comparisons with a caveat.

## Notes on scope

- **Historical depth** — the `/days` endpoint returns each sensor's full history (2016–2026), not the 2-year window requested via `datetime_from`. The raw layer keeps everything; window to a shorter period in staging if needed (`WHERE date_utc >= '2024-01-01'`).
- **Metro-area matching** — `capital_name` tags each station with the capital whose ~33 km box it fell into. It approximates the metropolitan area, so Athens correctly includes stations in Maroussi, Kifisia, and other Attica municipalities. It is not an official metro boundary, just a fixed-radius geographic proxy.