"""Command-line entry point for acquiring the pinned official Synthea data."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.ingestion.synthea_loader import acquire_synthea_data


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download and validate the required official Synthea CSV files."
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path("data/raw/synthea"),
        help="Destination for unmodified source CSVs (default: data/raw/synthea).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing CSVs only when their checksums differ.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    metadata = acquire_synthea_data(
        output_directory=args.output_directory,
        overwrite=args.overwrite,
    )
    for item in metadata:
        logging.info(
            "%s: %d rows, %d bytes, sha256=%s",
            item.filename,
            item.row_count,
            item.size_bytes,
            item.sha256,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
