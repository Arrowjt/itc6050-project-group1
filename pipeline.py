"""
Air quality data pipeline.

Ingests OpenAQ v3 data (locations, sensors, measurements) for ~85 world
capitals into the `raw` schema of the `air_quality` Postgres database.

Run inside the Docker Compose network:
    make pipeline
    # or:
    docker compose --profile manual run --rm pipeline

Test with a smaller window and fewer capitals:
    docker compose --profile manual run --rm \\
        -e WINDOW_DAYS=7 -e CAPITALS_LIMIT=3 \\
        pipeline python pipeline.py
"""

import os
import sys
from dotenv import load_dotenv

import dlt

from sources.openaq import (
    locations_resource,
    sensors_resource,
    measurements_resource,
)
from sources.restcountries import countries_resource

# Load .env when running locally. Inside the container, env vars are
# already injected by docker compose, so load_dotenv is a no-op.
load_dotenv()


def _build_credentials() -> dict:
    """Assemble Postgres credentials from env vars for the dlt destination."""
    required = ("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB",
                "POSTGRES_USER", "POSTGRES_PASSWORD")
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        print(f"Missing env vars: {missing}", file=sys.stderr)
        sys.exit(1)
    return {
        "drivername": "postgresql",
        "host": os.getenv("POSTGRES_HOST"),
        "port": int(os.getenv("POSTGRES_PORT")),
        "database": os.getenv("POSTGRES_DB"),
        "username": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
    }


def main() -> int:
    creds = _build_credentials()

    pipeline = dlt.pipeline(
        pipeline_name="openaq_ingest",
        destination=dlt.destinations.postgres(credentials=creds),
        dataset_name="raw",
        progress="log",
    )

    print(f"Pipeline: {pipeline.pipeline_name}")
    print(f"Destination: postgres @ {creds['host']}:{creds['port']}/{creds['database']}")
    print(f"Dataset:  {pipeline.dataset_name}")
    print()

    info = pipeline.run(
        [
            countries_resource(),
            locations_resource(),
            sensors_resource(),
            measurements_resource(),
        ]
    )
    print()
    print(info)
    return 0


if __name__ == "__main__":
    sys.exit(main())