-- Executed by the PostgreSQL image only when the data volume is initialized.
-- The database itself is created by POSTGRES_DB in docker-compose.yml.
CREATE SCHEMA IF NOT EXISTS raw AUTHORIZATION CURRENT_USER;
CREATE SCHEMA IF NOT EXISTS staging AUTHORIZATION CURRENT_USER;
CREATE SCHEMA IF NOT EXISTS analytics AUTHORIZATION CURRENT_USER;
