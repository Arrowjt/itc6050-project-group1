"""
Explore OpenAQ v3 data availability for world capitals.

Uses REST Countries API to get the list of capitals + coordinates,
then queries OpenAQ v3 with a bounding box around each capital to
count active monitoring stations and note data availability.

Output: scripts/capitals_report.csv — one row per country/capital.

NOT part of the production pipeline. This is disposable exploration
code to inform the geographic scope decision.
"""

import os
import time
from datetime import datetime, timezone, timedelta

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

OPENAQ_KEY = os.getenv("OPENAQ_API_KEY")
if not OPENAQ_KEY:
    raise SystemExit("OPENAQ_API_KEY not set in .env")

OPENAQ_BASE = "https://api.openaq.org/v3"

# Bounding box radius around a capital's coordinates, in degrees.
# ~0.3 degrees = ~33 km at the equator, covers most metro areas.
BBOX_HALF_WIDTH = 0.3

# Consider a station "active" if it reported within this window
ACTIVE_WITHIN_DAYS = 30

session = requests.Session()
session.headers.update({"X-API-Key": OPENAQ_KEY})


def fetch_capitals():
    """Fetch capitals from REST Countries v5 (paginated)."""
    key = os.getenv("RESTCOUNTRIES_API_KEY")
    if not key:
        raise SystemExit("RESTCOUNTRIES_API_KEY not set in .env")

    print("Fetching capitals from REST Countries v5...")
    url = "https://api.restcountries.com/countries/v5"
    headers = {"Authorization": f"Bearer {key}"}
    params_base = {
        "response_fields": "names.common,codes.alpha_2,capitals",
        "limit": 100,
    }

    out = []
    offset = 0
    while True:
        params = {**params_base, "offset": offset}
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        payload = resp.json()

        objects = payload["data"]["objects"]
        for c in objects:
            name = c.get("names", {}).get("common")
            code = c.get("codes", {}).get("alpha_2") or ""
            capitals = c.get("capitals") or []
            if not name or not code or not capitals:
                continue
            primary = next(
                (cap for cap in capitals if cap.get("attributes", {}).get("primary")),
                capitals[0],
            )
            coords = primary.get("coordinates") or {}
            lat, lng = coords.get("lat"), coords.get("lng")
            if lat is None or lng is None:
                continue
            out.append({
                "country": name,
                "cca2": code,
                "capital": primary.get("name"),
                "lat": lat,
                "lon": lng,
            })

        meta = payload["data"]["meta"]
        if not meta.get("more"):
            break
        offset += meta["count"]

    print(f"  Got {len(out)} capitals with codes and coordinates.")
    return out

def bbox_around(lat, lon, half=BBOX_HALF_WIDTH):
    """Return an OpenAQ bbox string: min_lon,min_lat,max_lon,max_lat."""
    return f"{lon - half},{lat - half},{lon + half},{lat + half}"


def survey_capital(country, cca2, capital, lat, lon):
    """Query OpenAQ for locations near this capital and summarise."""
    bbox = bbox_around(lat, lon)
    url = f"{OPENAQ_BASE}/locations"
    params = {"bbox": bbox, "limit": 1000}

    try:
        resp = session.get(url, params=params, timeout=30)
        resp.raise_for_status()
    except requests.HTTPError as e:
        return {
            "country": country, "cca2": cca2, "capital": capital,
            "total_locations": None, "active_locations": None,
            "earliest_data": None, "latest_data": None,
            "sensors_total": None, "error": str(e),
        }

    data = resp.json()
    results = data.get("results", [])
    total = len(results)

    cutoff = datetime.now(timezone.utc) - timedelta(days=ACTIVE_WITHIN_DAYS)
    active = 0
    earliest = None
    latest = None
    sensors_total = 0

    for loc in results:
        dtl = loc.get("datetimeLast") or {}
        dtf = loc.get("datetimeFirst") or {}
        last_utc = dtl.get("utc")
        first_utc = dtf.get("utc")

        if last_utc:
            last_dt = datetime.fromisoformat(last_utc.replace("Z", "+00:00"))
            if last_dt >= cutoff:
                active += 1
            if latest is None or last_dt > latest:
                latest = last_dt
        if first_utc:
            first_dt = datetime.fromisoformat(first_utc.replace("Z", "+00:00"))
            if earliest is None or first_dt < earliest:
                earliest = first_dt

        sensors_total += len(loc.get("sensors") or [])

    return {
        "country": country, "cca2": cca2, "capital": capital,
        "total_locations": total,
        "active_locations": active,
        "earliest_data": earliest.date().isoformat() if earliest else None,
        "latest_data": latest.date().isoformat() if latest else None,
        "sensors_total": sensors_total,
        "error": None,
    }


def main():
    capitals = fetch_capitals()

    limit = int(os.getenv("EXPLORE_LIMIT", "0"))
    if limit > 0:
        capitals = capitals[:limit]
        print(f"  (limited to first {limit} for testing)")

    rows = []
    for i, c in enumerate(capitals, start=1):
        print(f"[{i:3d}/{len(capitals)}] {c['country']:30s} -> {c['capital']}")
        row = survey_capital(**c)
        rows.append(row)
        time.sleep(0.15)  # polite pacing, well under rate limit

    df = pd.DataFrame(rows)
    df = df.sort_values(by=["active_locations", "sensors_total"], ascending=False, na_position="last")

    out_path = "scripts/capitals_report.csv"
    df.to_csv(out_path, index=False)
    print(f"\nWrote {out_path}")

    covered = df[df["active_locations"] > 0]
    print(f"\nSummary:")
    print(f"  Capitals surveyed:                 {len(df)}")
    print(f"  Capitals with any OpenAQ data:     {(df['total_locations'] > 0).sum()}")
    print(f"  Capitals with active stations:     {len(covered)}")
    print(f"  Total active stations across all:  {int(covered['active_locations'].sum())}")

    print(f"\nTop 15 capitals by active station count:")
    print(covered.head(15)[["country", "capital", "active_locations", "sensors_total", "earliest_data"]].to_string(index=False))


if __name__ == "__main__":
    main()