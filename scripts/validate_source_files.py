"""Validate existing Synthea source files and refresh their inventory."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.ingestion.synthea_loader import (
    DEFAULT_INVENTORY_FILENAME,
    SYNTHEA_ARCHIVE_SHA256,
    SYNTHEA_SOURCE_URL,
    validate_synthea_directory,
    write_inventory,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate required Synthea CSVs without changing source files."
    )
    parser.add_argument(
        "--directory",
        type=Path,
        default=Path("data/raw/synthea"),
        help="Directory containing Synthea source CSVs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    metadata = validate_synthea_directory(args.directory)
    existing_inventory_path = args.directory / DEFAULT_INVENTORY_FILENAME
    acquired_at = None
    source_url = SYNTHEA_SOURCE_URL
    source_archive_sha256 = SYNTHEA_ARCHIVE_SHA256
    if existing_inventory_path.is_file():
        existing_inventory = json.loads(
            existing_inventory_path.read_text(encoding="utf-8")
        )
        acquired_at = datetime.fromisoformat(existing_inventory["acquired_at_utc"])
        source_url = existing_inventory["source_url"]
        source_archive_sha256 = existing_inventory["source_archive_sha256"]

    inventory_path = write_inventory(
        args.directory,
        metadata,
        acquired_at=acquired_at,
        source_url=source_url,
        source_archive_sha256=source_archive_sha256,
    )
    for item in metadata:
        logging.info(
            "%s: %d rows, %d bytes, sha256=%s",
            item.filename,
            item.row_count,
            item.size_bytes,
            item.sha256,
        )
    logging.info("Inventory written to %s", inventory_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
