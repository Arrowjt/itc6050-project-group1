"""
Configuration constants for the OpenAQ pipeline.

All tunable values live here — window size, bounding box radius, rate limits.
Change the WINDOW_DAYS to shorten/lengthen the ingestion window.
"""

import os

# API endpoints
OPENAQ_BASE = "https://api.openaq.org/v3"
RESTCOUNTRIES_BASE = "https://api.restcountries.com/countries/v5"

# Ingestion window
# Overridable at runtime via the WINDOW_DAYS env variable for testing.
WINDOW_DAYS = int(os.getenv("WINDOW_DAYS", "730"))  # 24 months default

# Capital selection
# Overridable at runtime via CAPITALS_LIMIT for testing (0 = all).
CAPITALS_LIMIT = int(os.getenv("CAPITALS_LIMIT", "0"))

# Filter capitals by comma-separated ISO alpha-2 codes (e.g., "GR,JP,TH").
# Empty string = no filter.
CAPITALS_FILTER = [
    c.strip().upper()
    for c in os.getenv("CAPITALS_FILTER", "").split(",")
    if c.strip()
]

# Bounding box half-width in degrees around each capital's coordinates.
# ~0.3 degrees = ~33 km at the equator. Covers most metro areas.
BBOX_HALF_WIDTH = 0.3

# Consider a station "active" if its datetimeLast is within this many days.
ACTIVE_WITHIN_DAYS = 30

# Pagination
LOCATIONS_PAGE_SIZE = 1000
MEASUREMENTS_PAGE_SIZE = 1000

# Rate limiting — polite pause between API calls.
# OpenAQ's stated limit is "generous" but not documented as a specific rate.
# 100ms = 10 req/sec, safely under any reasonable cap.
POLITE_SLEEP_SECONDS = 1.5  # OpenAQ free tier: 60 req/min, using ~40 req/min for safety margin
# Request timeouts
HTTP_TIMEOUT_SECONDS = 60