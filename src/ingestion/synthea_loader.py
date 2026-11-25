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
import uuid
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Final, Iterable, Iterator, Sequence

import pandas as pd
from sqlalchemy import BigInteger, DateTime, Engine, Text, text
from sqlalchemy.exc import SQLAlchemyError

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
DEFAULT_DATABASE_SCHEMA: Final = "raw"
DEFAULT_INGESTION_CHUNK_SIZE: Final = 25_000
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


class SyntheaIngestionError(RuntimeError):
    """Raised when a validated Synthea file cannot be loaded and reconciled."""


@dataclass(frozen=True, slots=True)
class FileMetadata:
    """Validated metadata for one unmodified Synthea CSV file."""

    filename: str
    source_member: str
    size_bytes: int
    row_count: int
    sha256: str
    headers: list[str]


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """Reconciliation result for one source file and raw database table."""

    filename: str
    table_name: str
    source_row_count: int
    loaded_row_count: int
    difference: int
    load_id: str
    status: str


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


def _quote_identifier(identifier: str) -> str:
    """Quote a trusted SQL identifier and reject embedded null characters."""
    if "\x00" in identifier:
        raise SyntheaIngestionError("SQL identifiers cannot contain null characters.")
    return '"' + identifier.replace('"', '""') + '"'


def _table_name(filename: str) -> str:
    """Return the raw table name for a selected CSV filename."""
    if filename not in EXPECTED_HEADERS:
        raise SyntheaIngestionError(f"Unsupported Synthea source file: {filename}")
    return Path(filename).stem


def _read_csv_chunks(path: Path, chunk_size: int) -> Iterator[pd.DataFrame]:
    """Stream source values as text while retaining literals such as 'NA'."""
    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1.")
    try:
        yield from pd.read_csv(
            path,
            dtype=str,
            keep_default_na=False,
            na_filter=False,
            encoding="utf-8-sig",
            chunksize=chunk_size,
        )
    except (OSError, UnicodeError, pd.errors.ParserError) as exc:
        raise SyntheaIngestionError(f"Unable to parse {path}: {exc}") from exc


def _prepare_chunk(
    chunk: pd.DataFrame,
    filename: str,
    load_id: str,
    loaded_at_utc: datetime,
    first_source_row: int,
) -> pd.DataFrame:
    """Convert blank source fields to null and append deterministic lineage."""
    prepared = chunk.mask(chunk.eq(""), None)
    prepared["_source_filename"] = filename
    prepared["_source_row_number"] = range(
        first_source_row, first_source_row + len(prepared)
    )
    prepared["_load_id"] = load_id
    prepared["_loaded_at_utc"] = loaded_at_utc
    return prepared


def _database_types(source_headers: Sequence[str]) -> dict[str, object]:
    """Return explicit SQL types for source and lineage columns."""
    return {
        **{column: Text() for column in source_headers},
        "_source_filename": Text(),
        "_source_row_number": BigInteger(),
        "_load_id": Text(),
        "_loaded_at_utc": DateTime(timezone=True),
    }


def load_synthea_csv(
    engine: Engine,
    path: Path,
    *,
    schema: str = DEFAULT_DATABASE_SCHEMA,
    chunk_size: int = DEFAULT_INGESTION_CHUNK_SIZE,
) -> IngestionResult:
    """Atomically load one validated Synthea CSV and reconcile its row count.

    Source fields are stored as database text so ingestion cannot silently alter
    identifiers, dates, codes, or synthetic monetary values. Type conversion is
    deliberately deferred to the staging layer.
    """
    filename = path.name
    expected_headers = EXPECTED_HEADERS.get(filename)
    if expected_headers is None:
        raise SyntheaIngestionError(f"Unsupported Synthea source file: {filename}")

    try:
        source_row_count, _ = validate_csv(path, expected_headers)
        source_sha256 = _sha256(path)
    except SyntheaValidationError as exc:
        raise SyntheaIngestionError(str(exc)) from exc
    table_name = _table_name(filename)
    load_id = str(uuid.uuid4())
    loaded_at_utc = datetime.now(timezone.utc)
    temporary_table = f"_{table_name}_{load_id.replace('-', '')[:12]}"
    qualified_temporary = (
        f"{_quote_identifier(schema)}.{_quote_identifier(temporary_table)}"
    )
    qualified_target = f"{_quote_identifier(schema)}.{_quote_identifier(table_name)}"
    rows_written = 0
    created = False

    LOGGER.info(
        "synthea_load_started file=%s table=%s source_rows=%d load_id=%s",
        filename,
        f"{schema}.{table_name}",
        source_row_count,
        load_id,
    )
    try:
        with engine.begin() as connection:
            for chunk in _read_csv_chunks(path, chunk_size):
                if list(chunk.columns) != list(expected_headers):
                    raise SyntheaIngestionError(
                        f"Unexpected header while loading {filename}."
                    )
                prepared = _prepare_chunk(
                    chunk,
                    filename,
                    load_id,
                    loaded_at_utc,
                    rows_written + 1,
                )
                prepared.to_sql(
                    temporary_table,
                    connection,
                    schema=schema,
                    if_exists="append" if created else "fail",
                    index=False,
                    dtype=_database_types(expected_headers),
                )
                created = True
                rows_written += len(prepared)

            if not created:
                empty = pd.DataFrame(columns=[
                    *expected_headers,
                    "_source_filename",
                    "_source_row_number",
                    "_load_id",
                    "_loaded_at_utc",
                ])
                empty.to_sql(
                    temporary_table,
                    connection,
                    schema=schema,
                    if_exists="fail",
                    index=False,
                    dtype=_database_types(expected_headers),
                )

            loaded_row_count = int(
                connection.execute(
                    text(f"SELECT COUNT(*) FROM {qualified_temporary}")
                ).scalar_one()
            )
            if source_row_count != rows_written or source_row_count != loaded_row_count:
                raise SyntheaIngestionError(
                    f"Row-count reconciliation failed for {filename}: "
                    f"source={source_row_count}, written={rows_written}, "
                    f"database={loaded_row_count}."
                )
            if _sha256(path) != source_sha256:
                raise SyntheaIngestionError(
                    f"Source file changed during ingestion: {path}"
                )

            connection.execute(text(f"DROP TABLE IF EXISTS {qualified_target}"))
            connection.execute(
                text(
                    f"ALTER TABLE {qualified_temporary} "
                    f"RENAME TO {_quote_identifier(table_name)}"
                )
            )
    except (SQLAlchemyError, SyntheaIngestionError) as exc:
        LOGGER.exception(
            "synthea_load_failed file=%s table=%s load_id=%s",
            filename,
            f"{schema}.{table_name}",
            load_id,
        )
        if isinstance(exc, SyntheaIngestionError):
            raise
        raise SyntheaIngestionError(
            f"Database load failed for {filename}: {exc}"
        ) from exc

    result = IngestionResult(
        filename=filename,
        table_name=f"{schema}.{table_name}",
        source_row_count=source_row_count,
        loaded_row_count=loaded_row_count,
        difference=loaded_row_count - source_row_count,
        load_id=load_id,
        status="reconciled",
    )
    LOGGER.info(
        "synthea_load_completed file=%s table=%s source_rows=%d "
        "loaded_rows=%d difference=%d status=%s load_id=%s",
        result.filename,
        result.table_name,
        result.source_row_count,
        result.loaded_row_count,
        result.difference,
        result.status,
        result.load_id,
    )
    return result


def load_synthea_directory(
    engine: Engine,
    directory: Path = DEFAULT_OUTPUT_DIRECTORY,
    *,
    schema: str = DEFAULT_DATABASE_SCHEMA,
    chunk_size: int = DEFAULT_INGESTION_CHUNK_SIZE,
) -> list[IngestionResult]:
    """Load and reconcile every selected Synthea CSV in deterministic order."""
    results = []
    for filename in EXPECTED_HEADERS:
        results.append(
            load_synthea_csv(
                engine,
                directory / filename,
                schema=schema,
                chunk_size=chunk_size,
            )
        )
    return results
