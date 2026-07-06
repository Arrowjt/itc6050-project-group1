"""
REST Countries v5 fetcher and dlt resource.

Serves two purposes:
  1. Populates raw.countries with country metadata (name, codes, region, capital)
  2. Provides the capitals list that drives OpenAQ location queries

REST Countries v5 requires a free API key. Register at:
    https://restcountries.com/sign-up
"""

import os
import time
from datetime import datetime, timezone
from typing import Iterator, Dict, Any, List

import dlt
import requests

from .config import (
    RESTCOUNTRIES_BASE,
    HTTP_TIMEOUT_SECONDS,
    POLITE_SLEEP_SECONDS,
)

_RESTCOUNTRIES_FIELDS = (
    "names.common,codes.alpha_2,codes.alpha_3,capitals,"
    "region,subregion,population,area"
)

def _session() -> requests.Session:
    key = os.getenv("RESTCOUNTRIES_API_KEY")
    if not key:
        raise RuntimeError("RESTCOUNTRIES_API_KEY not set")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {key}"})
    return s


def _fetch_all_countries() -> List[Dict[str, Any]]:
    """Paginated fetch of all countries from REST Countries v5."""
    session = _session()
    all_countries: List[Dict[str, Any]] = []
    offset = 0
    limit = 100

    while True:
        params = {
            "response_fields": _RESTCOUNTRIES_FIELDS,
            "limit": limit,
            "offset": offset,
        }
        resp = session.get(RESTCOUNTRIES_BASE, params=params, timeout=HTTP_TIMEOUT_SECONDS)
        resp.raise_for_status()
        payload = resp.json()

        objects = payload["data"]["objects"]
        all_countries.extend(objects)

        meta = payload["data"]["meta"]
        if not meta.get("more"):
            break
        offset += meta["count"]
        time.sleep(POLITE_SLEEP_SECONDS)

    return all_countries


def _flatten_country(c: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten a REST Countries record into a flat row."""
    codes = c.get("codes") or {}
    region = c.get("region")
    subregion = c.get("subregion")
    capitals = c.get("capitals") or []

    primary = None
    if capitals:
        primary = next(
            (cap for cap in capitals if (cap.get("attributes") or {}).get("primary")),
            capitals[0],
        )

    cap_name, cap_lat, cap_lon = None, None, None
    if primary:
        cap_name = primary.get("name")
        coords = primary.get("coordinates") or {}
        cap_lat = coords.get("lat")
        cap_lon = coords.get("lng")

    return {
        "country_name": (c.get("names") or {}).get("common"),
        "alpha_2": codes.get("alpha_2") or None,
        "alpha_3": codes.get("alpha_3") or None,
        "region": region,
        "subregion": subregion,
        "population": c.get("population"),
        "area_sq_km": c.get("area"),
        "capital_name": cap_name,
        "capital_lat": cap_lat,
        "capital_lon": cap_lon,
    }


def get_capitals_for_openaq() -> List[Dict[str, Any]]:
    """
    Return capitals in the format openaq.py expects:
        [{country, cca2, capital, lat, lon}, ...]
    Filters out entries with no alpha_2 code or coordinates.
    Result is cached on function attr so we call REST Countries once per run.
    """
    cached = getattr(get_capitals_for_openaq, "_cache", None)
    if cached is not None:
        return cached

    raw = _fetch_all_countries()
    caps: List[Dict[str, Any]] = []
    for c in raw:
        flat = _flatten_country(c)
        if not flat["alpha_2"] or flat["capital_lat"] is None:
            continue
        caps.append({
            "country": flat["country_name"],
            "cca2": flat["alpha_2"],
            "capital": flat["capital_name"],
            "lat": flat["capital_lat"],
            "lon": flat["capital_lon"],
        })

    get_capitals_for_openaq._cache = caps
    return caps


@dlt.resource(name="countries", write_disposition="merge", primary_key="alpha_2")
def countries_resource() -> Iterator[Dict[str, Any]]:
    """Yield country dimension rows for raw.countries."""
    print("Fetching countries from REST Countries v5...")
    raw = _fetch_all_countries()
    print(f"  Fetched {len(raw)} countries from REST Countries")

    now_utc = datetime.now(timezone.utc).isoformat()
    for c in raw:
        flat = _flatten_country(c)
        if not flat["alpha_2"]:
            continue
        flat["ingested_at"] = now_utc
        yield flat