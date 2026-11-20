"""Acquire and validate the pinned official Synthea CSV source files."""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Final, Iterable, Sequence

LOGGER = logging.getLogger(__name__)

SYNTHEA_SOURCE_URL: Final = (
    "https://synthetichealth.github.io/synthea-sample-data/downloads/"
    "synthea_sample_data_csv_nov2021.zip"
)
SYNTHEA_ARCHIVE_SHA256: Final = (
    "870b68a127f3570ca964e89e49dd3433cf3e7a27cc4079d2bff5f094be0a43c2"
)
DEFAULT_OUTPUT_DIRECTORY: Final = Path("data/raw/synthea")
DEFAULT_INVENTORY_FILENAME: Final = "_inventory.json"
DOWNLOAD_CHUNK_SIZE: Final = 1024 * 1024

EXPECTED_HEADERS: Final[dict[str, tuple[str, ...]]] = {
    "patients.csv": (
        "Id", "BIRTHDATE", "DEATHDATE", "SSN", "DRIVERS", "PASSPORT",
        "PREFIX", "FIRST", "LAST", "SUFFIX", "MAIDEN", "MARITAL", "RACE",
        "ETHNICITY", "GENDER", "BIRTHPLACE", "ADDRESS", "CITY", "STATE",
        "COUNTY", "ZIP", "LAT", "LON", "HEALTHCARE_EXPENSES",
        "HEALTHCARE_COVERAGE",
    ),
    "encounters.csv": (
        "Id", "START", "STOP", "PATIENT", "ORGANIZATION", "PROVIDER", "PAYER",
        "ENCOUNTERCLASS", "CODE", "DESCRIPTION", "BASE_ENCOUNTER_COST",
        "TOTAL_CLAIM_COST", "PAYER_COVERAGE", "REASONCODE", "REASONDESCRIPTION",
    ),
    "procedures.csv": (
        "START", "STOP", "PATIENT", "ENCOUNTER", "CODE", "DESCRIPTION",
        "BASE_COST", "REASONCODE", "REASONDESCRIPTION",
    ),
    "medications.csv": (
        "START", "STOP", "PATIENT", "PAYER", "ENCOUNTER", "CODE", "DESCRIPTION",
        "BASE_COST", "PAYER_COVERAGE", "DISPENSES", "TOTALCOST", "REASONCODE",
        "REASONDESCRIPTION",
    ),
    "conditions.csv": (
        "START", "STOP", "PATIENT", "ENCOUNTER", "CODE", "DESCRIPTION",
    ),
    "claims.csv": (
        "Id", "PATIENTID", "PROVIDERID", "PRIMARYPATIENTINSURANCEID",
        "SECONDARYPATIENTINSURANCEID", "DEPARTMENTID", "PATIENTDEPARTMENTID",
        "DIAGNOSIS1", "DIAGNOSIS2", "DIAGNOSIS3", "DIAGNOSIS4", "DIAGNOSIS5",
        "DIAGNOSIS6", "DIAGNOSIS7", "DIAGNOSIS8", "REFERRINGPROVIDERID",
        "APPOINTMENTID", "CURRENTILLNESSDATE", "SERVICEDATE",
        "SUPERVISINGPROVIDERID", "STATUS1", "STATUS2", "STATUSP", "OUTSTANDING1",
        "OUTSTANDING2", "OUTSTANDINGP", "LASTBILLEDDATE1", "LASTBILLEDDATE2",
        "LASTBILLEDDATEP", "HEALTHCARECLAIMTYPEID1", "HEALTHCARECLAIMTYPEID2",
    ),
    "claims_transactions.csv": (
        "ID", "CLAIMID", "CHARGEID", "PATIENTID", "TYPE", "AMOUNT", "METHOD",
        "FROMDATE", "TODATE", "PLACEOFSERVICE", "PROCEDURECODE", "MODIFIER1",
        "MODIFIER2", "DIAGNOSISREF1", "DIAGNOSISREF2", "DIAGNOSISREF3",
        "DIAGNOSISREF4", "UNITS", "DEPARTMENTID", "NOTES", "UNITAMOUNT",
        "TRANSFEROUTID", "TRANSFERTYPE", "PAYMENTS", "ADJUSTMENTS", "TRANSFERS",
        "OUTSTANDING", "APPOINTMENTID", "LINENOTE", "PATIENTINSURANCEID",
        "FEESCHEDULEID", "PROVIDERID", "SUPERVISINGPROVIDERID",
    ),
    "payers.csv": (
        "Id", "NAME", "ADDRESS", "CITY", "STATE_HEADQUARTERED", "ZIP", "PHONE",
        "AMOUNT_COVERED", "AMOUNT_UNCOVERED", "REVENUE", "COVERED_ENCOUNTERS",
        "UNCOVERED_ENCOUNTERS", "COVERED_MEDICATIONS", "UNCOVERED_MEDICATIONS",
        "COVERED_PROCEDURES", "UNCOVERED_PROCEDURES", "COVERED_IMMUNIZATIONS",
        "UNCOVERED_IMMUNIZATIONS", "UNIQUE_CUSTOMERS", "QOLS_AVG", "MEMBER_MONTHS",
    ),
}


class SyntheaAcquisitionError(RuntimeError):
    """Raised when the official Synthea archive cannot be safely acquired."""


class SyntheaValidationError(ValueError):
    """Raised when a Synthea source file fails structural validation."""


@dataclass(frozen=True, slots=True)
class FileMetadata:
    """Validated metadata for one unmodified Synthea CSV file."""

    filename: str
    source_member: str
    size_bytes: int
    row_count: int
    sha256: str
    headers: list[str]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(DOWNLOAD_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_archive(source_url: str, destination: Path) -> None:
    request = urllib.request.Request(
        source_url,
        headers={"User-Agent": "healthcare-revenue-cycle-reconciliation/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            response_status = getattr(response, "status", None)
            if response_status not in {None, 200}:
                raise SyntheaAcquisitionError(
                    f"Synthea download returned HTTP {response_status}."
                )
            with destination.open("wb") as archive:
                shutil.copyfileobj(response, archive, length=DOWNLOAD_CHUNK_SIZE)
    except (OSError, urllib.error.URLError) as exc:
        raise SyntheaAcquisitionError(
            f"Unable to download the official Synthea archive: {exc}"
        ) from exc


def _required_archive_members(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    members: dict[str, zipfile.ZipInfo] = {}
    for member in archive.infolist():
        filename = PurePosixPath(member.filename).name
        if filename not in EXPECTED_HEADERS:
            continue
        if filename in members:
            raise SyntheaAcquisitionError(
                f"Archive contains duplicate required filename: {filename}"
            )
        members[filename] = member

    missing = sorted(set(EXPECTED_HEADERS) - set(members))
    if missing:
        raise SyntheaAcquisitionError(
            "Official archive is missing required files: " + ", ".join(missing)
        )
    return members


def validate_csv(path: Path, expected_headers: Sequence[str]) -> tuple[int, list[str]]:
    """Stream-validate a CSV's header and record widths, returning its row count."""
    if not path.is_file():
        raise SyntheaValidationError(f"Required source file does not exist: {path}")
    if path.stat().st_size == 0:
        raise SyntheaValidationError(f"Required source file is empty: {path}")

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.reader(source)
            headers = next(reader, None)
            if headers is None:
                raise SyntheaValidationError(f"CSV has no header: {path}")
            if headers != list(expected_headers):
                raise SyntheaValidationError(
                    f"Unexpected header in {path.name}. Expected {list(expected_headers)!r}; "
                    f"received {headers!r}."
                )

            row_count = 0
            expected_width = len(headers)
            for record_number, row in enumerate(reader, start=2):
                if len(row) != expected_width:
                    raise SyntheaValidationError(
                        f"{path.name} record {record_number} has {len(row)} fields; "
                        f"expected {expected_width}."
                    )
                row_count += 1
    except (OSError, UnicodeError, csv.Error) as exc:
        raise SyntheaValidationError(f"Unable to validate {path}: {exc}") from exc

    return row_count, headers


def validate_synthea_directory(
    directory: Path = DEFAULT_OUTPUT_DIRECTORY,
    source_members: dict[str, str] | None = None,
) -> list[FileMetadata]:
    """Validate all required source files and return their inventory metadata."""
    metadata: list[FileMetadata] = []
    for filename, expected_headers in EXPECTED_HEADERS.items():
        path = directory / filename
        row_count, headers = validate_csv(path, expected_headers)
        metadata.append(
            FileMetadata(
                filename=filename,
                source_member=(source_members or {}).get(filename, f"csv/{filename}"),
                size_bytes=path.stat().st_size,
                row_count=row_count,
                sha256=_sha256(path),
                headers=headers,
            )
        )
    return metadata


def write_inventory(
    directory: Path,
    files: Iterable[FileMetadata],
    acquired_at: datetime | None = None,
    source_url: str = SYNTHEA_SOURCE_URL,
    source_archive_sha256: str = SYNTHEA_ARCHIVE_SHA256,
) -> Path:
    """Write source provenance and validated file metadata atomically."""
    inventory_path = directory / DEFAULT_INVENTORY_FILENAME
    validation_time = datetime.now(timezone.utc)
    payload = {
        "dataset": "Synthea 1K sample synthetic patient records (CSV, November 2021)",
        "synthetic_data_notice": (
            "All records and financial fields are synthetic and do not represent "
            "actual patients, hospitals, or financial performance."
        ),
        "source_url": source_url,
        "source_archive_sha256": source_archive_sha256,
        "acquired_at_utc": (acquired_at or validation_time).isoformat(),
        "validated_at_utc": validation_time.isoformat(),
        "files": [asdict(item) for item in files],
    }
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=directory, suffix=".tmp", delete=False
    ) as temporary_file:
        json.dump(payload, temporary_file, indent=2)
        temporary_file.write("\n")
        temporary_path = Path(temporary_file.name)
    os.replace(temporary_path, inventory_path)
    return inventory_path


def acquire_synthea_data(
    output_directory: Path = DEFAULT_OUTPUT_DIRECTORY,
    source_url: str = SYNTHEA_SOURCE_URL,
    expected_archive_sha256: str = SYNTHEA_ARCHIVE_SHA256,
    overwrite: bool = False,
) -> list[FileMetadata]:
    """Download, checksum, extract, validate, and inventory required source CSVs."""
    output_directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="synthea-acquisition-", dir=output_directory.parent
    ) as work_directory:
        work_path = Path(work_directory)
        archive_path = work_path / "synthea.zip"
        staged_directory = work_path / "csv"
        staged_directory.mkdir()

        LOGGER.info("Downloading official Synthea archive from %s", source_url)
        _download_archive(source_url, archive_path)
        archive_sha256 = _sha256(archive_path)
        if archive_sha256.lower() != expected_archive_sha256.lower():
            raise SyntheaAcquisitionError(
                "Downloaded archive checksum mismatch. "
                f"Expected {expected_archive_sha256}; received {archive_sha256}."
            )

        try:
            with zipfile.ZipFile(archive_path) as archive:
                members = _required_archive_members(archive)
                for filename, member in members.items():
                    destination = staged_directory / filename
                    with archive.open(member) as source, destination.open("wb") as target:
                        shutil.copyfileobj(source, target, length=DOWNLOAD_CHUNK_SIZE)
        except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
            raise SyntheaAcquisitionError(
                f"Unable to extract the official Synthea archive: {exc}"
            ) from exc

        source_members = {
            filename: member.filename for filename, member in members.items()
        }
        staged_metadata = validate_synthea_directory(
            staged_directory, source_members=source_members
        )

        for item in staged_metadata:
            existing_path = output_directory / item.filename
            if not existing_path.exists():
                continue
            existing_sha256 = _sha256(existing_path)
            if existing_sha256 != item.sha256 and not overwrite:
                raise SyntheaAcquisitionError(
                    f"Refusing to replace existing source file {existing_path}. "
                    "Use --overwrite only after reviewing the checksum difference."
                )

        for item in staged_metadata:
            staged_path = staged_directory / item.filename
            destination = output_directory / item.filename
            if destination.exists() and _sha256(destination) == item.sha256:
                continue
            os.replace(staged_path, destination)

    final_metadata = validate_synthea_directory(
        output_directory, source_members=source_members
    )
    write_inventory(
        output_directory,
        final_metadata,
        source_url=source_url,
        source_archive_sha256=expected_archive_sha256,
    )
    LOGGER.info("Validated %d required Synthea source files.", len(final_metadata))
    return final_metadata
