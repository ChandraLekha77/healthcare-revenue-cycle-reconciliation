# Healthcare Revenue Cycle Reconciliation

Production-oriented data engineering project for reconciling synthetic Synthea
healthcare encounters, claims, and payments with supporting public reference
data. Synthea financial fields are synthetic and must not be interpreted as
actual hospital financial performance.

## Day 2: local PostgreSQL

### Prerequisites

- Docker Desktop with Docker Compose
- Python 3.11 or later

### Configure the environment

Copy the environment template and replace the password with a strong local-only
value. The `.env` file is ignored by Git and must never be committed.

```powershell
Copy-Item .env.example .env
```

All database settings are supplied through environment variables. Docker
Compose reads `.env` automatically. Python processes must have the same values
in their environment; one local option is:

```powershell
Get-Content .env | ForEach-Object {
    if ($_ -and -not $_.StartsWith('#')) {
        $name, $value = $_ -split '=', 2
        [Environment]::SetEnvironmentVariable($name, $value, 'Process')
    }
}
```

### Start and verify PostgreSQL

```powershell
docker compose up -d postgres
docker compose ps
docker compose exec postgres psql -U $env:POSTGRES_USER `
    -d $env:POSTGRES_DB -c "\dn"
```

On first initialization, PostgreSQL creates the database named by
`POSTGRES_DB` and the `raw`, `staging`, and `analytics` schemas. The named
Docker volume preserves data across ordinary container restarts.

Verify the application connection from Python:

```powershell
python -c "from src.database import create_database_engine, verify_database_connection; engine = create_database_engine(); print(verify_database_connection(engine)); engine.dispose()"
```

### Stop PostgreSQL

Stop containers while preserving the database volume:

```powershell
docker compose down
```

To restart the existing database:

```powershell
docker compose up -d postgres
```

Removing the named volume permanently deletes the local database and causes the
initialization SQL to run again on the next startup. Use this only when a full
local reset is intentional:

```powershell
docker compose down --volumes
```

## Day 3: acquire official Synthea CSV data

Download the pinned official November 2021 Synthea CSV sample, extract only the
eight project source tables, validate them, and create a data inventory:

```powershell
python scripts/download_synthea_data.py
```

Revalidate the local raw files without downloading them again:

```powershell
python scripts/validate_source_files.py
```

The raw CSVs remain byte-for-byte copies of the official archive and are ignored
by Git. See `data/README.md` for source provenance and validation details.
