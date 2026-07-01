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

For development, we work from a frozen snapshot of the OpenAQ data so everyone gets identical results in dbt tests and dashboard screenshots. The pipeline itself supports incremental refresh — you can `make pipeline` any time to pull fresh data.

To restore the shared snapshot (link in the team Google Drive folder):

```bash
# After downloading raw_snapshot.sql.gz to your machine
gunzip -c raw_snapshot.sql.gz | docker compose exec -T postgres psql -U postgres -d air_quality
```

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

- **OpenAQ API** — https://docs.openaq.org (no authentication required)
- **Open-Meteo API** — https://open-meteo.com (no authentication required)

## Troubleshooting

**"Port 5433 already in use"** — you have another Postgres running on that port. Stop it, or edit `POSTGRES_PORT` in your `.env` and the `ports:` line in `docker-compose.yml` to a free port (e.g., 5434).

**"Cannot connect to Docker daemon"** — Docker Desktop is not running. Start it.

**Windows: `make` command not found** — install Make via Chocolatey (`choco install make`) or run commands directly from the Makefile (e.g., `docker compose up -d postgres dashboard`).

**Something broke and I want to start over** — `make clean` removes containers, networks, and the database volume. Then `make setup && make up`.

## License

Academic project, not licensed for reuse.
