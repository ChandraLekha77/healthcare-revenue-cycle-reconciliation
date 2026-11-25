"""Load and reconcile the selected Synthea CSVs into PostgreSQL raw tables."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.database import (
    DatabaseConfigurationError,
    DatabaseConnectionError,
    create_database_engine,
    verify_database_connection,
)
from src.ingestion.synthea_loader import (
    DEFAULT_INGESTION_CHUNK_SIZE,
    DEFAULT_OUTPUT_DIRECTORY,
    SyntheaIngestionError,
    load_synthea_directory,
)
from src.utils.logging_config import configure_logging


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Load Synthea CSVs into PostgreSQL raw tables."
    )
    parser.add_argument(
        "--source-directory",
        type=Path,
        default=DEFAULT_OUTPUT_DIRECTORY,
        help="Directory containing the eight validated Synthea CSV files.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_INGESTION_CHUNK_SIZE,
        help="CSV rows processed per Pandas chunk.",
    )
    return parser.parse_args()


def main() -> int:
    """Run the complete Synthea raw ingestion and print reconciliation results."""
    configure_logging()
    arguments = parse_arguments()
    if arguments.chunk_size < 1:
        raise SystemExit("--chunk-size must be at least 1")

    try:
        engine = create_database_engine()
    except DatabaseConfigurationError as exc:
        print(f"Database configuration failed: {exc}", file=sys.stderr)
        return 2
    try:
        verify_database_connection(engine)
        results = load_synthea_directory(
            engine,
            arguments.source_directory,
            chunk_size=arguments.chunk_size,
        )
    except (DatabaseConnectionError, SyntheaIngestionError) as exc:
        print(f"Raw ingestion failed: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    print("filename,table,source_rows,loaded_rows,difference,status")
    for result in results:
        print(
            f"{result.filename},{result.table_name},{result.source_row_count},"
            f"{result.loaded_row_count},{result.difference},{result.status}"
        )
    return 0 if all(result.difference == 0 for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
