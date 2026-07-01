-- Automatically executed on first Postgres container startup
-- (Postgres runs any .sql file in /docker-entrypoint-initdb.d/)

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS analytics;

-- Grants to the app user (currently the same as the superuser)
GRANT ALL PRIVILEGES ON SCHEMA raw TO postgres;
GRANT ALL PRIVILEGES ON SCHEMA analytics TO postgres;
