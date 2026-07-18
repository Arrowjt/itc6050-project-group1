"""
OpenAQ v3 dlt resources for the air quality pipeline.

Three resources:
  - locations:         monitoring stations near each capital (bbox query)
  - sensors:           extracted inline from the locations response (no extra calls)
  - measurements_daily: daily average per sensor (/days endpoint), over WINDOW_DAYS

All resources use write_disposition="merge" with a primary key,
so re-running the pipeline appends new data and updates changed rows
without duplicating history.
"""

import os
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Iterator, Dict, Any, List, Optional, Set

import dlt
import requests
import pandas as pd

from .config import (
    OPENAQ_BASE,
    WINDOW_DAYS,
    CAPITALS_LIMIT,
    CAPITALS_FILTER,
    BBOX_HALF_WIDTH,
    ACTIVE_WITHIN_DAYS,
    LOCATIONS_PAGE_SIZE,
    MEASUREMENTS_PAGE_SIZE,
    POLITE_SLEEP_SECONDS,
    HTTP_TIMEOUT_SECONDS,
)


# ----------------------------------------------------------------------
# HTTP session shared across all resources
# ----------------------------------------------------------------------

def _session() -> requests.Session:
    """Create a requests session with the OpenAQ auth header."""
    key = os.getenv("OPENAQ_API_KEY")
    if not key:
        raise RuntimeError("OPENAQ_API_KEY not set")
    s = requests.Session()
    s.headers.update({"X-API-Key": key})
    return s


def _get(session: requests.Session, url: str, params: Optional[dict] = None,
         max_retries: int = 5) -> dict:
    """
    GET with proactive rate-limit pacing and retries on transient errors.

    Retries on:
      - 429 Too Many Requests (using Retry-After or exponential backoff)
      - 5xx server errors
      - Network timeouts and connection errors

    Uses OpenAQ's x-ratelimit-* headers to proactively pace requests.
    """
    for attempt in range(max_retries):
        try:
            resp = session.get(url, params=params or {}, timeout=HTTP_TIMEOUT_SECONDS)
        except (requests.Timeout, requests.ConnectionError) as e:
            wait = 2 ** (attempt + 1)
            print(f"    network error ({type(e).__name__}), retry {attempt + 1}/{max_retries} in {wait}s")
            time.sleep(wait)
            continue

        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 2 ** (attempt + 1)))
            print(f"    429 received, sleeping {wait}s...")
            time.sleep(wait)
            continue

        if resp.status_code >= 500:
            wait = 2 ** (attempt + 1)
            print(f"    server error {resp.status_code}, retry {attempt + 1}/{max_retries} in {wait}s")
            time.sleep(wait)
            continue

        resp.raise_for_status()

        # Proactive pacing using OpenAQ's rate limit headers
        remaining = resp.headers.get("x-ratelimit-remaining")
        reset = resp.headers.get("x-ratelimit-reset")
        if remaining is not None and reset is not None:
            try:
                if int(remaining) <= 2:
                    time.sleep(int(reset) + 1)
                else:
                    time.sleep(POLITE_SLEEP_SECONDS)
            except ValueError:
                time.sleep(POLITE_SLEEP_SECONDS)
        else:
            time.sleep(POLITE_SLEEP_SECONDS)

        return resp.json()

    raise requests.HTTPError(f"Max retries exceeded for {url}")
# ----------------------------------------------------------------------
# Checkpoint state — track completed sensors so restarts skip them
# ----------------------------------------------------------------------

STATE_DIR = "/app/.pipeline_state"
STATE_FILE = os.path.join(STATE_DIR, "completed_sensors.json")


def _load_completed_sensors() -> Set[int]:
    """Load the set of sensor IDs that finished in a prior run."""
    if not os.path.exists(STATE_FILE):
        return set()
    try:
        with open(STATE_FILE, "r") as f:
            return set(json.load(f))
    except Exception as e:
        print(f"  Warning: could not read state file: {e}")
        return set()


def _mark_sensor_completed(sensor_id: int, completed: Set[int]) -> None:
    """Add sensor to completed set and flush to disk."""
    completed.add(sensor_id)
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(sorted(completed), f)
    os.replace(tmp, STATE_FILE)  # atomic on POSIX

# ----------------------------------------------------------------------
# Capitals loader (from static CSV committed alongside the pipeline)
# ----------------------------------------------------------------------

def _load_capitals() -> List[Dict[str, Any]]:
    """
    Load capitals from REST Countries v5 via sources.restcountries.
    Applies CAPITALS_FILTER first, then CAPITALS_LIMIT.
    """
    from .restcountries import get_capitals_for_openaq
    caps = get_capitals_for_openaq()
    if CAPITALS_FILTER:
        caps = [c for c in caps if c["cca2"] in CAPITALS_FILTER]
    if CAPITALS_LIMIT > 0:
        caps = caps[:CAPITALS_LIMIT]
    return caps

def _bbox(lat: float, lon: float) -> str:
    """Return a bounding box string: min_lon,min_lat,max_lon,max_lat."""
    h = BBOX_HALF_WIDTH
    return f"{lon - h},{lat - h},{lon + h},{lat + h}"


def _is_active(datetime_last_utc: Optional[str]) -> bool:
    """Location is active if it reported within ACTIVE_WITHIN_DAYS."""
    if not datetime_last_utc:
        return False
    dt = datetime.fromisoformat(datetime_last_utc.replace("Z", "+00:00"))
    cutoff = datetime.now(timezone.utc) - timedelta(days=ACTIVE_WITHIN_DAYS)
    return dt >= cutoff


# ----------------------------------------------------------------------
# Fetch locations + sensors for all capitals (one API call per capital)
# ----------------------------------------------------------------------

def _fetch_all_locations(session: requests.Session) -> List[Dict[str, Any]]:
    """
    Iterate over capitals and fetch active locations near each.
    Returns raw location dicts, tagged with (capital_country, capital_name).
    """
    capitals = _load_capitals()
    print(f"  Loaded {len(capitals)} capitals to survey")

    all_locations = []
    for i, cap in enumerate(capitals, start=1):
        url = f"{OPENAQ_BASE}/locations"
        params = {"bbox": _bbox(cap["lat"], cap["lon"]), "limit": LOCATIONS_PAGE_SIZE}
        try:
            payload = _get(session, url, params)
        except requests.HTTPError as e:
            print(f"  [{i:3d}/{len(capitals)}] {cap['capital']:25s} skipped ({e})")
            continue
        results = payload.get("results", [])
        active = [r for r in results if _is_active((r.get("datetimeLast") or {}).get("utc"))]
        # tag each active location with which capital it belongs to
        for r in active:
            r["_capital_country"] = cap["country"]
            r["_capital_name"] = cap["capital"]
            r["_capital_cca2"] = cap["cca2"]
        print(f"  [{i:3d}/{len(capitals)}] {cap['capital']:25s} -> {len(active):3d} active locations")
        all_locations.extend(active)
    return all_locations


# ----------------------------------------------------------------------
# dlt resources
# ----------------------------------------------------------------------

@dlt.resource(name="locations", write_disposition="merge", primary_key="location_id")
def locations_resource() -> Iterator[Dict[str, Any]]:
    """
    Yield one row per active monitoring station near a surveyed capital.
    Also stashes the raw dict list on the resource function attribute so the
    sensors + measurements resources can reuse it without re-hitting the API.
    """
    session = _session()
    print("Fetching locations from OpenAQ...")
    raw = _fetch_all_locations(session)
    print(f"  Total active locations: {len(raw)}")

    # Stash for downstream resources
    locations_resource.raw_locations = raw

    now_utc = datetime.now(timezone.utc).isoformat()
    for loc in raw:
        country = loc.get("country") or {}
        provider = loc.get("provider") or {}
        coords = loc.get("coordinates") or {}
        dtf = loc.get("datetimeFirst") or {}
        dtl = loc.get("datetimeLast") or {}
        yield {
            "location_id": loc["id"],
            "name": loc.get("name"),
            "locality": loc.get("locality"),
            "country_id": country.get("id"),
            "country_code": country.get("code"),
            "country_name": country.get("name"),
            "capital_country": loc.get("_capital_country"),
            "capital_name": loc.get("_capital_name"),
            "capital_cca2": loc.get("_capital_cca2"),
            "latitude": coords.get("latitude"),
            "longitude": coords.get("longitude"),
            "timezone": loc.get("timezone"),
            "provider_id": provider.get("id"),
            "provider_name": provider.get("name"),
            "is_mobile": loc.get("isMobile"),
            "is_monitor": loc.get("isMonitor"),
            "datetime_first_utc": dtf.get("utc"),
            "datetime_last_utc": dtl.get("utc"),
            "ingested_at": now_utc,
        }


@dlt.resource(name="sensors", write_disposition="merge", primary_key="sensor_id")
def sensors_resource() -> Iterator[Dict[str, Any]]:
    """
    Extract sensor rows from the locations already fetched.
    Requires locations_resource() to have run in the same pipeline call.
    """
    raw = getattr(locations_resource, "raw_locations", None)
    if raw is None:
        raise RuntimeError("locations_resource must run before sensors_resource")

    now_utc = datetime.now(timezone.utc).isoformat()
    for loc in raw:
        for sensor in loc.get("sensors") or []:
            param = sensor.get("parameter") or {}
            yield {
                "sensor_id": sensor["id"],
                "location_id": loc["id"],
                "sensor_name": sensor.get("name"),
                "parameter_id": param.get("id"),
                "parameter_name": param.get("name"),
                "parameter_units": param.get("units"),
                "parameter_display_name": param.get("displayName"),
                "ingested_at": now_utc,
            }


@dlt.resource(
    name="measurements_daily",
    write_disposition="merge",
    primary_key=["sensor_id", "date_utc"],
)
def measurements_resource() -> Iterator[Dict[str, Any]]:
    """
    Fetch daily-average measurements for every sensor in the run using the
    OpenAQ /days endpoint. Each row is one sensor-day with the daily mean
    plus summary stats and coverage (for the 75% completeness rule).
    Filters to the last WINDOW_DAYS. Injects sensor_id into each row.
    """
    raw = getattr(locations_resource, "raw_locations", None)
    if raw is None:
        raise RuntimeError("locations_resource must run before measurements_resource")

    session = _session()
    date_from = (datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)).isoformat()
    date_to = datetime.now(timezone.utc).isoformat()

    # Flatten out all sensors
    sensor_ids = [
        s["id"]
        for loc in raw
        for s in (loc.get("sensors") or [])
    ]
    total = len(sensor_ids)
    completed = _load_completed_sensors()
    if completed:
        print(f"Resuming: {len(completed)} sensors already completed from previous run")
    remaining = [s for s in sensor_ids if s not in completed]
    print(f"Fetching daily measurements for {len(remaining)} sensors ({total} total, window: {WINDOW_DAYS} days)...")

    now_utc = datetime.now(timezone.utc).isoformat()
    failed_sensors = []
    for i, sensor_id in enumerate(remaining, start=1):
        page = 1
        page_count = 0
        try:
            while True:
                url = f"{OPENAQ_BASE}/sensors/{sensor_id}/days"
                params = {
                    "datetime_from": date_from,
                    "datetime_to": date_to,
                    "limit": MEASUREMENTS_PAGE_SIZE,
                    "page": page,
                }
                payload = _get(session, url, params)
                results = payload.get("results", [])
                if not results:
                    break
                for m in results:
                    period = m.get("period") or {}
                    dtf = period.get("datetimeFrom") or {}
                    dtt = period.get("datetimeTo") or {}
                    param = m.get("parameter") or {}
                    coverage = m.get("coverage") or {}
                    summary = m.get("summary") or {}
                    yield {
                        "sensor_id": sensor_id,
                        "date_utc": dtf.get("utc"),
                        "date_local": dtf.get("local"),
                        "datetime_to_utc": dtt.get("utc"),
                        "value_avg": m.get("value"),
                        "value_min": summary.get("min"),
                        "value_max": summary.get("max"),
                        "value_median": summary.get("median"),
                        "value_sd": summary.get("sd"),
                        "parameter_id": param.get("id"),
                        "parameter_name": param.get("name"),
                        "parameter_units": param.get("units"),
                        "expected_count": coverage.get("expectedCount"),
                        "observed_count": coverage.get("observedCount"),
                        "percent_complete": coverage.get("percentComplete"),
                        "period_label": period.get("label"),
                        "ingested_at": now_utc,
                    }
                page_count += len(results)
                if len(results) < MEASUREMENTS_PAGE_SIZE:
                    break
                page += 1
        except Exception as e:
            failed_sensors.append((sensor_id, str(e)))
            print(f"  sensor {sensor_id} skipped after retries: {e}")
            continue
        _mark_sensor_completed(sensor_id, completed)
        if i % 20 == 0 or i == len(remaining):
            print(f"  [{i:4d}/{len(remaining)}] sensor {sensor_id} -> {page_count} rows")
            
    if failed_sensors:
        print(f"\n  Skipped {len(failed_sensors)} sensors due to unrecoverable errors:")
        for sid, err in failed_sensors[:10]:
            print(f"    {sid}: {err}")
        if len(failed_sensors) > 10:
            print(f"    ... and {len(failed_sensors) - 10} more")