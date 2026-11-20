"""Unit tests for Synthea source acquisition and validation."""

from __future__ import annotations

import csv
import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from src.ingestion.synthea_loader import (
    EXPECTED_HEADERS,
    SyntheaAcquisitionError,
    SyntheaValidationError,
    acquire_synthea_data,
    validate_csv,
)


def write_header_only_csv(path: Path, headers: tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as target:
        csv.writer(target, lineterminator="\n").writerow(headers)


def build_test_archive(path: Path) -> str:
    source_directory = path.parent / "archive-source"
    source_directory.mkdir()
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, headers in EXPECTED_HEADERS.items():
            source_path = source_directory / filename
            write_header_only_csv(source_path, headers)
            archive.write(source_path, arcname=f"csv/{filename}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_validate_csv_accepts_exact_header_and_reports_zero_rows(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "patients.csv"
    write_header_only_csv(csv_path, EXPECTED_HEADERS["patients.csv"])

    row_count, headers = validate_csv(csv_path, EXPECTED_HEADERS["patients.csv"])

    assert row_count == 0
    assert headers == list(EXPECTED_HEADERS["patients.csv"])


def test_validate_csv_rejects_changed_header(tmp_path: Path) -> None:
    csv_path = tmp_path / "patients.csv"
    write_header_only_csv(csv_path, ("WRONG",))

    with pytest.raises(SyntheaValidationError, match="Unexpected header"):
        validate_csv(csv_path, EXPECTED_HEADERS["patients.csv"])


def test_acquisition_extracts_required_files_and_writes_inventory(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "synthea.zip"
    archive_sha256 = build_test_archive(archive_path)
    output_directory = tmp_path / "raw"

    metadata = acquire_synthea_data(
        output_directory=output_directory,
        source_url=archive_path.as_uri(),
        expected_archive_sha256=archive_sha256,
    )

    assert {item.filename for item in metadata} == set(EXPECTED_HEADERS)
    assert all(item.row_count == 0 for item in metadata)
    inventory = json.loads((output_directory / "_inventory.json").read_text())
    assert len(inventory["files"]) == len(EXPECTED_HEADERS)
    assert inventory["source_url"] == archive_path.as_uri()
    assert inventory["source_archive_sha256"] == archive_sha256
    assert inventory["validated_at_utc"]

    repeated_metadata = acquire_synthea_data(
        output_directory=output_directory,
        source_url=archive_path.as_uri(),
        expected_archive_sha256=archive_sha256,
    )
    assert [item.sha256 for item in repeated_metadata] == [
        item.sha256 for item in metadata
    ]


def test_acquisition_rejects_archive_checksum_mismatch(tmp_path: Path) -> None:
    archive_path = tmp_path / "synthea.zip"
    build_test_archive(archive_path)

    with pytest.raises(SyntheaAcquisitionError, match="checksum mismatch"):
        acquire_synthea_data(
            output_directory=tmp_path / "raw",
            source_url=archive_path.as_uri(),
            expected_archive_sha256="0" * 64,
        )
