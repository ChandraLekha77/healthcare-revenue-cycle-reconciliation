"""Acquire or validate the version-pinned official CMS reference archives."""

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

from src.ingestion.cms_loader import (
    CMS_SOURCES,
    DEFAULT_INVENTORY_FILENAME,
    acquire_cms_data,
    validate_cms_directory,
    write_inventory,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download and validate the selected official CMS archives."
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path("data/raw/cms"),
        help="Destination for preserved CMS ZIP archives.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate existing archives without downloading them.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing archive only when its checksum differs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if args.validate_only:
        metadata = validate_cms_directory(args.output_directory)
        inventory_path = args.output_directory / DEFAULT_INVENTORY_FILENAME
        acquired_at = None
        if inventory_path.is_file():
            existing_inventory = json.loads(
                inventory_path.read_text(encoding="utf-8")
            )
            acquired_at = datetime.fromisoformat(
                existing_inventory["acquired_at_utc"]
            )
        write_inventory(
            args.output_directory,
            metadata,
            CMS_SOURCES,
            acquired_at=acquired_at,
        )
    else:
        metadata = acquire_cms_data(
            output_directory=args.output_directory,
            overwrite=args.overwrite,
        )

    for archive in metadata:
        logging.info(
            "%s: %d bytes, %d members, sha256=%s",
            archive.filename,
            archive.size_bytes,
            archive.member_count,
            archive.sha256,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
