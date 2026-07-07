# ITC 6050 — Group 1: Global Air Quality Monitor

End-to-end data pipeline ingesting air quality measurements from the OpenAQ API, transforming them with dbt, and visualising results in Streamlit.

Course project for ITC 6050 Data Engineering, Spring 2026, Deree — The American College of Greece. Instructor: Dr. Maira Kotsovoulou. Submission: 21 July 2026.

## Team

- Ioannis Tsantilas — Ingestion & Infrastructure
- [Teammate B] — Transformation & Data Quality
- [Teammate C] — Dashboard & Presentation

## Stack

- **Ingestion:** dlt
- **Storage:** PostgreSQL 16
- **Transformation:** dbt (dbt-postgres)
- **Dashboard:** Streamlit
- **Orchestration:** Docker Compose
- **Enrichment:** Open-Meteo weather API (stretch goal)

Everything runs in Docker containers, so you do not need to install Python, Postgres, dbt, or Streamlit on your machine. You only need Docker Desktop.

## Prerequisites

- **OpenAQ API key** — free, register at https://explore.openaq.org/register. You'll need this before running the pipeline.
- **Docker Desktop** — https://www.docker.com/products/docker-desktop
  - macOS: install and launch. That's it.
  - Windows: install with the WSL2 backend enabled. Follow the Docker install wizard prompts.
- **Git** — https://git-scm.com
- **Make** — preinstalled on macOS and most Linux. On Windows, install via `choco install make` or use WSL2.

Optional (recommended for inspecting the database):
- **DBeaver Community** — https://dbeaver.io/download/

## Quick start

Five commands from a fresh clone to a running dashboard.

```bash
git clone https://github.com/Arrowjt/itc6050-project-group1.git
cd itc6050-project-group1
make setup       # Creates .env from template and builds Docker images (~5 min first time)
make up          # Starts Postgres and Streamlit dashboard in the background
make pipeline    # Runs the ingestion pipeline (populates the raw schema)
make dbt-run     # Builds the transformation models
```

Then open the dashboard: http://localhost:8501

## Everyday commands

Run `make` (or `make help`) to see all available commands. The most common:

| Command | Purpose |
|---|---|
| `make up` | Start Postgres and dashboard |
| `make down` | Stop everything (data persists) |
| `make pipeline` | Refresh raw data from OpenAQ |
| `make dbt-run` | Rebuild the transformed models |
| `make dbt-test` | Run all data quality tests |
| `make psql` | Open a SQL shell inside Postgres |
| `make logs` | Watch container logs live |
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

If you want to pull fresh data from the API instead of restoring the snapshot:

```bash
make pipeline
```

This runs the full ingestion (several hours). It supports incremental re-runs — already-loaded rows are skipped via merge, and completed sensors are tracked in `.pipeline_state/` so an interrupted run resumes where it left off.

## Repository structure
## Repository structure

​```
itc6050-project-group1/
├── pipeline.py              # dlt ingestion script
├── dashboard.py             # Streamlit dashboard
├── requirements.txt         # Python dependencies
├── Dockerfile               # Shared image for pipeline/dbt/dashboard
├── docker-compose.yml       # Full stack orchestration
├── Makefile                 # One-command operations
├── .env.example             # Template for environment variables
├── db/
│   └── init.sql             # Schemas created on first Postgres startup
├── analytics/               # dbt project
│   └── models/
│       ├── sources.yml
│       ├── schema.yml
│       ├── stg_air_quality.sql
│       └── city_daily_avg.sql
└── docs/                    # Architecture diagram, screenshots
​```
## Data sources

- **OpenAQ API v3** — https://docs.openaq.org (free API key required, register at https://explore.openaq.org/register)

## Troubleshooting

**"Port 5433 already in use"** — you have another Postgres running on that port. Stop it, or edit `POSTGRES_PORT` in your `.env` and the `ports:` line in `docker-compose.yml` to a free port (e.g., 5434).

**"Cannot connect to Docker daemon"** — Docker Desktop is not running. Start it.

**Windows: `make` command not found** — install Make via Chocolatey (`choco install make`) or run commands directly from the Makefile (e.g., `docker compose up -d postgres dashboard`).

**Something broke and I want to start over** — `make clean` removes containers, networks, and the database volume. Then `make setup && make up`.

## License

Academic project, not licensed for reuse.
