# ITC 6050 — Group 1: Global Air Quality Monitor

End-to-end data pipeline ingesting air quality measurements from the OpenAQ API, transforming them with dbt, and visualising results in Streamlit.

Course project for ITC 6050 Data Engineering, Spring 2026, Deree — The American College of Greece. Instructor: Dr. Maira Kotsovoulou. Submission: 21 July 2026.

## Team

- Ioannis Tsantilas — Ingestion & Infrastructure
- Milena Mirumyan — Transformation & Data Quality
- Nikolaos Voudouris Bountouris — Dashboard & Presentation

## Stack

- **Ingestion:** dlt (OpenAQ v3 + REST Countries v5)
- **Storage:** PostgreSQL 16
- **Transformation:** dbt (dbt-postgres)
- **Dashboard:** Streamlit
- **Orchestration:** Docker Compose

Everything runs in Docker containers, so you do not need to install Python, Postgres, dbt, or Streamlit on your machine. You only need Docker Desktop.

## Prerequisites

- **Docker Desktop** — https://www.docker.com/products/docker-desktop
  - macOS: install and launch. That's it.
  - Windows: install with the WSL2 backend enabled. Follow the Docker install wizard prompts.
- **Git** — https://git-scm.com
- **Make** — preinstalled on macOS and most Linux. On Windows, install via `choco install make` or use WSL2.

Optional:
- **DBeaver Community** — https://dbeaver.io/download/ (for browsing the database with a GUI)
- **API keys** — only needed if you want to *refresh* the data from the APIs yourself (see "Refreshing the data"). For normal work you restore the shared snapshot and need no keys.

## Quick start

The pipeline takes several hours to run against the API, so you don't run it — you restore a shared database snapshot instead. Everyone works from the same ~7 million rows.

```bash
git clone https://github.com/Arrowjt/itc6050-project-group1.git
cd itc6050-project-group1
make setup       # Creates .env from template and builds Docker images (~5 min first time)
make up          # Starts Postgres and the Streamlit dashboard
```

Then restore the shared data snapshot (see "Working with the shared data snapshot" below), and you're ready to build dbt models and the dashboard.

## Everyday commands

Run `make` (or `make help`) to see all available commands. The most common:

| Command | Purpose |
|---|---|
| `make up` | Start Postgres and dashboard |
| `make down` | Stop everything (data persists) |
| `make dbt-run` | Rebuild the transformed models |
| `make dbt-test` | Run all data quality tests |
| `make psql` | Open a SQL shell inside Postgres |
| `make logs` | Watch container logs live |
| `make pipeline` | Refresh raw data from the APIs (slow, needs API keys — usually not needed) |
| `make clean` | Stop everything AND delete the database (use with caution) |

## Connecting DBeaver to the database

If you want to browse the data with a GUI:

- Host: `localhost`
- Port: `5433`   (not the default 5432 — we use 5433 to avoid conflicts with other Postgres instances)
- Database: `air_quality`
- Username: `postgres`
- Password: whatever you set in your `.env` file

## Working with the shared data snapshot

The pipeline takes several hours to run against the OpenAQ API, so you don't need to run it yourself. Instead, restore the shared database snapshot — everyone works from the same ~7 million rows of daily air quality data across 85 capitals (2016–2026).

The snapshot (`air_quality_raw.dump`, ~293 MB) is in the team Google Drive folder.

### Restore steps

1. Make sure the stack is running with an empty database:

   ```bash
   make setup
   make up
   ```

2. Download `air_quality_raw.dump` from the team Google Drive into the project folder.

3. Copy the dump into the Postgres container and restore it:

   ```bash
   docker compose cp ./air_quality_raw.dump postgres:/tmp/air_quality_raw.dump
   docker compose exec -T postgres pg_restore -U postgres -d air_quality \
     --no-owner --clean --if-exists /tmp/air_quality_raw.dump
   ```

4. Verify the restore (should return 7084417):

   ```bash
   docker compose exec postgres psql -U postgres -d air_quality \
     -c "SELECT COUNT(*) FROM raw.measurements_daily;"
   ```

The `--clean --if-exists` flags make the restore safe to re-run — it drops and recreates objects rather than erroring if they already exist.

### What's in the snapshot

The `raw` schema, four tables:

- `raw.countries` — country + capital metadata from REST Countries
- `raw.locations` — ~2,170 active monitoring stations near the 85 capitals
- `raw.sensors` — ~9,600 sensors (one per station-parameter pair)
- `raw.measurements_daily` — ~7.08M daily-average readings

See `docs/DATA_QUALITY_NOTES.md` for known data quality issues (mixed units, completeness, nulls) that the dbt staging layer needs to handle.

### Refreshing the data (optional)

If you want to pull fresh data from the APIs instead of restoring the snapshot, you need free API keys:

- **OpenAQ** — register at https://explore.openaq.org/register
- **REST Countries v5** — register at https://restcountries.com/sign-up

Put both in your `.env` (see `.env.example`), then:

```bash
make pipeline
```

This runs the full ingestion (several hours). It supports incremental re-runs — already-loaded rows are skipped via merge, and completed sensors are tracked in `.pipeline_state/` so an interrupted run resumes where it left off.

## Repository structure

```
itc6050-project-group1/
├── pipeline.py                 # dlt ingestion entry point
├── sources/                    # pipeline source modules
│   ├── config.py               # tunable constants (window, pacing, bbox)
│   ├── openaq.py               # OpenAQ resources: locations, sensors, measurements_daily
│   └── restcountries.py        # REST Countries resource: countries + capitals
├── scripts/                    # exploration / one-off scripts
│   └── explore_capitals.py     # capital data-availability survey
├── db/
│   └── init.sql                # schemas created on first Postgres startup
├── docs/
│   └── DATA_QUALITY_NOTES.md   # raw data quality findings for the dbt layer
├── analytics/                  # dbt project (Track B — in progress)
├── dashboard.py                # Streamlit dashboard (Track C — in progress)
├── requirements.txt            # Python dependencies
├── Dockerfile                  # shared image for pipeline/dbt/dashboard
├── docker-compose.yml          # full stack orchestration
├── Makefile                    # one-command operations
└── .env.example                # template for environment variables
```

Note: `analytics/` and `dashboard.py` are placeholders until Tracks B and C build them.

## Viewing the Dashboard (Track C)

The Streamlit dashboard lives on the `track-c-dashboard` branch. To view it:

1. Fetch and checkout the branch:
```bash
   git fetch origin
   git checkout track-c-dashboard
```

2. Build and start the stack (if not already running):
```bash
   docker compose build
   docker compose up -d
```

3. Restore the shared data snapshot (see "Working with the shared data snapshot" above).

4. Run dbt to build the analytics models:
```bash
   docker compose run --rm dbt seed
   docker compose run --rm dbt run
```

5. Restart the dashboard container to pick up the latest code:
```bash
   docker compose restart dashboard
```

6. Open your browser to: http://localhost:8501

The dashboard includes: KPI summary, top 10 most polluted cities (bar chart),
pollutant trend over time (line chart, selectable by city/pollutant), and a
WHO PM2.5 alert table with country/date filters.
## Data sources

- **OpenAQ API v3** — https://docs.openaq.org (free API key, register at https://explore.openaq.org/register)
- **REST Countries v5** — https://restcountries.com (free API key, register at https://restcountries.com/sign-up)

API keys are only required to refresh data. Restoring the snapshot needs no keys.

## Notes for developers

- **dlt staging schema:** during a pipeline run, dlt creates a temporary `raw_staging` schema as working space. It's harmless and can be dropped (`DROP SCHEMA raw_staging CASCADE;`). The shared snapshot excludes it.
- **Historical depth:** the OpenAQ `/days` endpoint returns each sensor's full history (2016–2026), not just a recent window. The raw layer keeps everything; window to a shorter period in dbt staging if needed (`WHERE date_utc >= '2024-01-01'`).

## Troubleshooting

**"Port 5433 already in use"** — you have another Postgres running on that port. Stop it, or edit `POSTGRES_PORT` in your `.env` and the `ports:` line in `docker-compose.yml` to a free port (e.g., 5434).

**"Cannot connect to Docker daemon"** — Docker Desktop is not running. Start it.

**Windows: `make` command not found** — install Make via Chocolatey (`choco install make`) or run commands directly from the Makefile (e.g., `docker compose up -d postgres dashboard`).

**Something broke and I want to start over** — `make clean` removes containers, networks, and the database volume. Then `make setup && make up`, and restore the snapshot again.

## License

Academic project, not licensed for reuse.
