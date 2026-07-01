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

## Repository structure
## Setup (local development)

Instructions will be added as the project develops. For now:

1. Clone the repo
2. Create a Python 3.12 virtual environment
3. Install dependencies: `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and fill in your local Postgres credentials
5. Restore the shared raw data dump (link shared separately with the team)

Full setup instructions and Docker Compose usage will be documented before submission.

## Data source

- **OpenAQ API** — https://docs.openaq.org (no authentication required)
- **Open-Meteo API** — https://open-meteo.com (no authentication required)

## License

Academic project, not licensed for reuse.
