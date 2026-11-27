"""Acquire and validate version-pinned CMS reference data archives."""

from __future__ import annotations

import csv
import hashlib
import io
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
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Final, Iterable, Iterator, Sequence

import pandas as pd
from sqlalchemy import BigInteger, Date, DateTime, Engine, Text, text
from sqlalchemy.exc import SQLAlchemyError

LOGGER = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIRECTORY: Final = Path("data/raw/cms")
DEFAULT_INVENTORY_FILENAME: Final = "_inventory.json"
DOWNLOAD_CHUNK_SIZE: Final = 1024 * 1024
DEFAULT_INGESTION_CHUNK_SIZE: Final = 25_000
DEFAULT_DATABASE_SCHEMA: Final = "raw"
ICD10_MEMBER: Final = "Code Descriptions/icd10cm_codes_2027.txt"
HCPCS_MEMBER: Final = "HCPC2026_OCT_ANWEB_09232026.xlsx"
MPFS_MEMBER: Final = "PPRRVU2026_Oct_nonQPP.csv"

HCPCS_COLUMNS: Final[dict[str, str]] = {
    "HCPC": "hcpcs_code",
    "SEQNUM": "sequence_number",
    "RECID": "record_identifier",
    "LONG DESCRIPTION": "long_description",
    "SHORT DESCRIPTION": "short_description",
    "PRICE1": "price_1",
    "PRICE2": "price_2",
    "PRICE3": "price_3",
    "PRICE4": "price_4",
    "MULT_PI": "multiple_pricing_indicator",
    "CIM1": "carrier_instruction_manual_1",
    "CIM2": "carrier_instruction_manual_2",
    "CIM3": "carrier_instruction_manual_3",
    "MCM1": "medicare_carrier_manual_1",
    "MCM2": "medicare_carrier_manual_2",
    "MCM3": "medicare_carrier_manual_3",
    "STATUTE": "statute",
    **{f"LABCERT{i}": f"lab_certification_{i}" for i in range(1, 9)},
    **{f"XREF{i}": f"cross_reference_{i}" for i in range(1, 6)},
    "COV": "coverage_code",
    "ASC_GRP": "asc_group",
    "ASC_DT": "asc_effective_date",
    "OPPS": "opps_code",
    "OPPS_PI": "opps_payment_indicator",
    "OPPS_DT": "opps_effective_date",
    "PROCNOTE": "processing_note_number",
    "BETOS": "betos_code",
    **{f"TOS{i}": f"type_of_service_{i}" for i in range(1, 6)},
    "ANEST_BU": "anesthesia_base_units",
    "ADD DT": "add_date",
    "ACT EFF DT": "action_effective_date",
    "TERM DT": "termination_date",
    "ACTION CD": "action_code",
}

MPFS_COLUMNS: Final[tuple[str, ...]] = (
    "hcpcs_code", "modifier", "description", "status_code",
    "medicare_payment_unused", "work_rvu", "nonfacility_pe_rvu",
    "nonfacility_na_indicator", "facility_pe_rvu", "facility_na_indicator",
    "malpractice_rvu", "total_nonfacility_rvu", "total_facility_rvu",
    "pctc_indicator", "global_surgery_days", "preoperative_percentage",
    "intraoperative_percentage", "postoperative_percentage",
    "multiple_procedure_indicator", "bilateral_surgery_indicator",
    "assistant_surgery_indicator", "cosurgeons_indicator",
    "team_surgery_indicator", "pricing_indicator", "endoscopic_base_code",
    "conversion_factor", "physician_supervision_code", "calculation_flag",
    "diagnostic_imaging_family", "opps_nonfacility_pe_rvu",
    "opps_facility_pe_rvu", "opps_malpractice_rvu",
)


class CMSAcquisitionError(RuntimeError):
    """Raised when an official CMS archive cannot be safely acquired."""


class CMSValidationError(ValueError):
    """Raised when a local CMS archive fails structural validation."""


class CMSIngestionError(RuntimeError):
    """Raised when a selected CMS reference cannot be loaded and reconciled."""


@dataclass(frozen=True, slots=True)
class CMSSource:
    """Pinned source metadata and validation requirements for one CMS archive."""

    dataset_id: str
    title: str
    filename: str
    source_url: str
    source_page: str
    sha256: str
    release_date: str
    effective_start: str
    effective_end: str
    required_members: tuple[str, ...]
    format_notes: str


@dataclass(frozen=True, slots=True)
class CMSArchiveMetadata:
    """Validated metadata for one preserved CMS source archive."""

    dataset_id: str
    filename: str
    size_bytes: int
    sha256: str
    member_count: int
    members: list[dict[str, int | str]]


@dataclass(frozen=True, slots=True)
class CMSIngestionResult:
    """Database row-count reconciliation for one CMS reference dataset."""

    dataset_id: str
    table_name: str
    source_row_count: int
    loaded_row_count: int
    difference: int
    load_id: str
    status: str


CMS_SOURCES: Final[tuple[CMSSource, ...]] = (
    CMSSource(
        dataset_id="icd10cm_fy2027",
        title="FY 2027 ICD-10-CM Code Descriptions in Tabular Order",
        filename="2027-code-descriptions-tabular-order.zip",
        source_url=(
            "https://www.cms.gov/files/zip/"
            "2027-code-descriptions-tabular-order.zip"
        ),
        source_page="https://www.cms.gov/medicare/coding-billing/ICD-10-codes",
        sha256=(
            "91c6c9d1117764ce72375a0f3a5493b1725dafbc1ab283b55799076c9e194965"
        ),
        release_date="not stated on CMS source page",
        effective_start="2026-10-01",
        effective_end="2027-09-30",
        required_members=(
            "Code Descriptions/icd10cm_codes_2027.txt",
            "Code Descriptions/icd10cm_order_2027.txt",
        ),
        format_notes=(
            "ZIP containing headerless fixed-width text files. Codes omit the "
            "display decimal and do not carry row-level effective dates."
        ),
    ),
    CMSSource(
        dataset_id="hcpcs_2026_q4",
        title="October 2026 Alpha-Numeric HCPCS File",
        filename="october-2026-alpha-numeric-hcpcs-file.zip",
        source_url=(
            "https://www.cms.gov/files/zip/"
            "october-2026-alpha-numeric-hcpcs-file.zip"
        ),
        source_page=(
            "https://www.cms.gov/medicare/coding-billing/"
            "healthcare-common-procedure-system/quarterly-update"
        ),
        sha256=(
            "08c2202fa92c1d1fb6f31b808b61c767bc487954f6930b6a0f8d09c89af5992f"
        ),
        release_date="2026-09-23",
        effective_start="2026-10-01",
        effective_end="2026-12-31",
        required_members=(
            "HCPC2026_OCT_ANWEB_09232026.txt",
            "HCPC2026_OCT_ANWEB_09232026.xlsx",
            "HCPC2026_recordlayout.txt",
        ),
        format_notes=(
            "ZIP containing fixed-width text, an Excel table, record layout, "
            "transaction report, corrections, NOC codes, and processing notes."
        ),
    ),
    CMSSource(
        dataset_id="mpfs_rvu26d",
        title="2026 Medicare Physician Fee Schedule RVU26D October Release",
        filename="rvu26d-updated-08-26-2026.zip",
        source_url=(
            "https://www.cms.gov/files/zip/rvu26d-updated-08-26-2026.zip"
        ),
        source_page=(
            "https://www.cms.gov/medicare/payment/fee-schedules/physician/"
            "pfs-relative-value-files/rvu26d"
        ),
        sha256=(
            "521ff0f4ecbf13b5d99dc1dc04d9f82e5361e55c6b4b6b3033043598bf8406e6"
        ),
        release_date="2026-08-26",
        effective_start="2026-10-01",
        effective_end="2026-12-31",
        required_members=(
            "PPRRVU2026_Oct_nonQPP.csv",
            "PPRRVU2026_Oct_QPP.csv",
            "GPCI2026.csv",
            "RVU26D.pdf",
        ),
        format_notes=(
            "ZIP containing CSV, fixed-width text, Excel, and PDF documentation. "
            "The primary RVU CSV uses a ten-row multi-line header."
        ),
    ),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(DOWNLOAD_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(source_url: str, destination: Path) -> None:
    request = urllib.request.Request(
        source_url,
        headers={"User-Agent": "healthcare-revenue-cycle-reconciliation/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            response_status = getattr(response, "status", None)
            if response_status not in {None, 200}:
                raise CMSAcquisitionError(
                    f"CMS download returned HTTP {response_status}: {source_url}"
                )
            with destination.open("wb") as target:
                shutil.copyfileobj(response, target, length=DOWNLOAD_CHUNK_SIZE)
    except (OSError, urllib.error.URLError) as exc:
        raise CMSAcquisitionError(
            f"Unable to download official CMS source {source_url}: {exc}"
        ) from exc


def validate_archive(path: Path, source: CMSSource) -> CMSArchiveMetadata:
    """Validate archive existence, checksum, ZIP integrity, and required members."""
    if not path.is_file():
        raise CMSValidationError(f"Required CMS archive does not exist: {path}")
    if path.stat().st_size == 0:
        raise CMSValidationError(f"Required CMS archive is empty: {path}")

    actual_sha256 = _sha256(path)
    if actual_sha256.lower() != source.sha256.lower():
        raise CMSValidationError(
            f"Checksum mismatch for {source.filename}. Expected {source.sha256}; "
            f"received {actual_sha256}."
        )

    try:
        with zipfile.ZipFile(path) as archive:
            corrupt_member = archive.testzip()
            if corrupt_member:
                raise CMSValidationError(
                    f"CRC validation failed for {source.filename}: {corrupt_member}"
                )
            archive_members = {item.filename: item for item in archive.infolist()}
            missing_members = sorted(
                set(source.required_members) - set(archive_members)
            )
            if missing_members:
                raise CMSValidationError(
                    f"{source.filename} is missing required members: "
                    + ", ".join(missing_members)
                )
            members = [
                {
                    "filename": item.filename,
                    "size_bytes": item.file_size,
                    "compressed_size_bytes": item.compress_size,
                }
                for item in archive.infolist()
                if not item.is_dir()
            ]
    except (OSError, zipfile.BadZipFile) as exc:
        raise CMSValidationError(f"Invalid ZIP archive {path}: {exc}") from exc

    return CMSArchiveMetadata(
        dataset_id=source.dataset_id,
        filename=source.filename,
        size_bytes=path.stat().st_size,
        sha256=actual_sha256,
        member_count=len(members),
        members=members,
    )


def validate_cms_directory(
    directory: Path = DEFAULT_OUTPUT_DIRECTORY,
    sources: Sequence[CMSSource] = CMS_SOURCES,
) -> list[CMSArchiveMetadata]:
    """Validate all expected CMS archives in a local raw-data directory."""
    return [validate_archive(directory / source.filename, source) for source in sources]


def write_inventory(
    directory: Path,
    archives: Sequence[CMSArchiveMetadata],
    sources: Sequence[CMSSource] = CMS_SOURCES,
    acquired_at: datetime | None = None,
) -> Path:
    """Write the CMS source-version inventory atomically."""
    source_lookup = {source.dataset_id: source for source in sources}
    now = datetime.now(timezone.utc)
    datasets = []
    for archive in archives:
        source = source_lookup[archive.dataset_id]
        datasets.append({**asdict(source), **asdict(archive)})

    payload = {
        "inventory_as_of": date.today().isoformat(),
        "acquired_at_utc": (acquired_at or now).isoformat(),
        "validated_at_utc": now.isoformat(),
        "selection_basis": (
            "Versions effective on 2026-11-23. Future-effective January 2027 "
            "HCPCS and MPFS releases were intentionally not selected."
        ),
        "datasets": datasets,
    }
    directory.mkdir(parents=True, exist_ok=True)
    inventory_path = directory / DEFAULT_INVENTORY_FILENAME
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=directory, suffix=".tmp", delete=False
    ) as temporary_file:
        json.dump(payload, temporary_file, indent=2)
        temporary_file.write("\n")
        temporary_path = Path(temporary_file.name)
    os.replace(temporary_path, inventory_path)
    return inventory_path


def acquire_cms_data(
    output_directory: Path = DEFAULT_OUTPUT_DIRECTORY,
    sources: Sequence[CMSSource] = CMS_SOURCES,
    overwrite: bool = False,
) -> list[CMSArchiveMetadata]:
    """Download pinned CMS archives, validate them, and record source metadata."""
    output_directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="cms-acquisition-", dir=output_directory.parent
    ) as work_directory:
        staging_directory = Path(work_directory)
        staged_metadata: list[CMSArchiveMetadata] = []
        for source in sources:
            staged_path = staging_directory / source.filename
            LOGGER.info("Downloading %s", source.title)
            _download(source.source_url, staged_path)
            staged_metadata.append(validate_archive(staged_path, source))

        for source, metadata in zip(sources, staged_metadata, strict=True):
            destination = output_directory / source.filename
            if destination.exists():
                existing_hash = _sha256(destination)
                if existing_hash != metadata.sha256 and not overwrite:
                    raise CMSAcquisitionError(
                        f"Refusing to replace {destination}; its checksum differs. "
                        "Use --overwrite only after reviewing the source version."
                    )

        for source, metadata in zip(sources, staged_metadata, strict=True):
            staged_path = staging_directory / source.filename
            destination = output_directory / source.filename
            if destination.exists() and _sha256(destination) == metadata.sha256:
                continue
            os.replace(staged_path, destination)

    final_metadata = validate_cms_directory(output_directory, sources)
    write_inventory(output_directory, final_metadata, sources)
    LOGGER.info("Validated %d CMS source archives.", len(final_metadata))
    return final_metadata


def _quote_identifier(identifier: str) -> str:
    """Quote a SQL identifier used by the controlled ingestion configuration."""
    if "\x00" in identifier:
        raise CMSIngestionError("SQL identifiers cannot contain null characters.")
    return '"' + identifier.replace('"', '""') + '"'


def _chunk_records(
    records: Iterable[dict[str, object]], chunk_size: int
) -> Iterator[pd.DataFrame]:
    """Yield bounded DataFrames from a source-specific record iterator."""
    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1.")
    batch: list[dict[str, object]] = []
    for record in records:
        batch.append(record)
        if len(batch) >= chunk_size:
            yield pd.DataFrame.from_records(batch)
            batch = []
    if batch:
        yield pd.DataFrame.from_records(batch)


def _icd10_chunks(
    archive: zipfile.ZipFile, chunk_size: int
) -> Iterator[pd.DataFrame]:
    """Parse the CMS headerless ICD-10-CM code-description fixed-width file."""
    def records() -> Iterator[dict[str, object]]:
        with archive.open(ICD10_MEMBER) as binary_source:
            source = io.TextIOWrapper(binary_source, encoding="utf-8-sig")
            for row_number, line in enumerate(source, start=1):
                raw_line = line.rstrip("\r\n")
                code = raw_line[:7].strip()
                description = raw_line[8:].rstrip() if len(raw_line) > 8 else ""
                if not code or not description:
                    raise CMSIngestionError(
                        f"Invalid ICD-10-CM record at source row {row_number}."
                    )
                yield {
                    "code": code,
                    "description": description,
                    "raw_record": raw_line,
                    "_source_row_number": row_number,
                }

    yield from _chunk_records(records(), chunk_size)


def _hcpcs_chunks(
    archive: zipfile.ZipFile, chunk_size: int
) -> Iterator[pd.DataFrame]:
    """Read the CMS HCPCS workbook and retain all 48 published source fields."""
    try:
        with archive.open(HCPCS_MEMBER) as source:
            frame = pd.read_excel(
                source,
                dtype=str,
                keep_default_na=False,
                engine="openpyxl",
            )
    except (OSError, ValueError) as exc:
        raise CMSIngestionError(f"Unable to read HCPCS workbook: {exc}") from exc
    if list(frame.columns) != list(HCPCS_COLUMNS):
        raise CMSIngestionError("HCPCS workbook columns do not match the pinned layout.")
    frame = frame.rename(columns=HCPCS_COLUMNS)
    if frame["hcpcs_code"].eq("").any():
        raise CMSIngestionError("HCPCS workbook contains a blank required code.")
    frame["_source_row_number"] = range(2, len(frame) + 2)
    for start in range(0, len(frame), chunk_size):
        yield frame.iloc[start : start + chunk_size].copy()


def _mpfs_chunks(
    archive: zipfile.ZipFile, chunk_size: int
) -> Iterator[pd.DataFrame]:
    """Parse the non-QPP MPFS CSV after its ten-row published header."""
    def records() -> Iterator[dict[str, object]]:
        with archive.open(MPFS_MEMBER) as binary_source:
            source = io.TextIOWrapper(binary_source, encoding="latin-1", newline="")
            reader = csv.reader(source)
            for _ in range(10):
                if next(reader, None) is None:
                    raise CMSIngestionError("MPFS CSV ended before its data header.")
            for row_number, row in enumerate(reader, start=11):
                if not row or not any(value.strip() for value in row):
                    continue
                if len(row) != len(MPFS_COLUMNS):
                    raise CMSIngestionError(
                        f"MPFS source row {row_number} has {len(row)} fields; "
                        f"expected {len(MPFS_COLUMNS)}."
                    )
                record = dict(zip(MPFS_COLUMNS, row, strict=True))
                if not record["hcpcs_code"]:
                    raise CMSIngestionError(
                        f"MPFS source row {row_number} has a blank HCPCS code."
                    )
                record["_source_row_number"] = row_number
                yield record

    yield from _chunk_records(records(), chunk_size)


def _add_lineage(
    frame: pd.DataFrame,
    source: CMSSource,
    member: str,
    load_id: str,
    loaded_at_utc: datetime,
) -> pd.DataFrame:
    """Convert source blanks to null and append archive-level provenance."""
    prepared = frame.mask(frame.eq(""), None)
    prepared["_dataset_id"] = source.dataset_id
    prepared["_source_archive"] = source.filename
    prepared["_source_member"] = member
    prepared["_effective_start"] = date.fromisoformat(source.effective_start)
    prepared["_effective_end"] = date.fromisoformat(source.effective_end)
    prepared["_load_id"] = load_id
    prepared["_loaded_at_utc"] = loaded_at_utc
    return prepared


def _database_types(columns: Sequence[str]) -> dict[str, object]:
    """Return explicit raw text and lineage types without semantic coercion."""
    types: dict[str, object] = {column: Text() for column in columns}
    types["_source_row_number"] = BigInteger()
    types["_effective_start"] = Date()
    types["_effective_end"] = Date()
    types["_loaded_at_utc"] = DateTime(timezone=True)
    return types


def _load_reference(
    engine: Engine,
    source: CMSSource,
    table_name: str,
    member: str,
    chunks: Iterable[pd.DataFrame],
    *,
    schema: str,
) -> CMSIngestionResult:
    """Atomically load parsed CMS chunks and reconcile parsed/database counts."""
    load_id = uuid.uuid4().hex
    loaded_at_utc = datetime.now(timezone.utc)
    temporary_table = f"_{table_name}_{load_id[:12]}"
    qualified_temporary = (
        f"{_quote_identifier(schema)}.{_quote_identifier(temporary_table)}"
    )
    qualified_target = f"{_quote_identifier(schema)}.{_quote_identifier(table_name)}"
    source_row_count = 0
    created = False
    LOGGER.info(
        "cms_load_started dataset=%s table=%s member=%s load_id=%s",
        source.dataset_id,
        f"{schema}.{table_name}",
        member,
        load_id,
    )
    try:
        with engine.begin() as connection:
            for frame in chunks:
                prepared = _add_lineage(
                    frame, source, member, load_id, loaded_at_utc
                )
                prepared.to_sql(
                    temporary_table,
                    connection,
                    schema=schema,
                    if_exists="append" if created else "fail",
                    index=False,
                    dtype=_database_types(list(prepared.columns)),
                )
                created = True
                source_row_count += len(prepared)
            if not created:
                raise CMSIngestionError(
                    f"Selected CMS member contains no data rows: {member}"
                )
            loaded_row_count = int(
                connection.execute(
                    text(f"SELECT COUNT(*) FROM {qualified_temporary}")
                ).scalar_one()
            )
            if loaded_row_count != source_row_count:
                raise CMSIngestionError(
                    f"Row-count reconciliation failed for {source.dataset_id}: "
                    f"source={source_row_count}, database={loaded_row_count}."
                )
            connection.execute(text(f"DROP TABLE IF EXISTS {qualified_target}"))
            connection.execute(
                text(
                    f"ALTER TABLE {qualified_temporary} "
                    f"RENAME TO {_quote_identifier(table_name)}"
                )
            )
    except (SQLAlchemyError, CMSIngestionError) as exc:
        LOGGER.exception(
            "cms_load_failed dataset=%s table=%s load_id=%s",
            source.dataset_id,
            f"{schema}.{table_name}",
            load_id,
        )
        if isinstance(exc, CMSIngestionError):
            raise
        raise CMSIngestionError(
            f"Database load failed for {source.dataset_id}: {exc}"
        ) from exc

    result = CMSIngestionResult(
        dataset_id=source.dataset_id,
        table_name=f"{schema}.{table_name}",
        source_row_count=source_row_count,
        loaded_row_count=loaded_row_count,
        difference=loaded_row_count - source_row_count,
        load_id=load_id,
        status="reconciled",
    )
    LOGGER.info(
        "cms_load_completed dataset=%s table=%s source_rows=%d "
        "loaded_rows=%d difference=%d status=%s load_id=%s",
        result.dataset_id,
        result.table_name,
        result.source_row_count,
        result.loaded_row_count,
        result.difference,
        result.status,
        result.load_id,
    )
    return result


def load_cms_references(
    engine: Engine,
    directory: Path = DEFAULT_OUTPUT_DIRECTORY,
    *,
    schema: str = DEFAULT_DATABASE_SCHEMA,
    chunk_size: int = DEFAULT_INGESTION_CHUNK_SIZE,
) -> list[CMSIngestionResult]:
    """Validate, load, and reconcile the three selected CMS references."""
    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1.")
    results: list[CMSIngestionResult] = []
    configurations = (
        (CMS_SOURCES[0], "cms_icd10cm_fy2027", ICD10_MEMBER, _icd10_chunks),
        (CMS_SOURCES[1], "cms_hcpcs_2026_q4", HCPCS_MEMBER, _hcpcs_chunks),
        (CMS_SOURCES[2], "cms_mpfs_rvu26d", MPFS_MEMBER, _mpfs_chunks),
    )
    for source, table_name, member, parser in configurations:
        archive_path = directory / source.filename
        validate_archive(archive_path, source)
        original_sha256 = _sha256(archive_path)
        try:
            with zipfile.ZipFile(archive_path) as archive:
                result = _load_reference(
                    engine,
                    source,
                    table_name,
                    member,
                    parser(archive, chunk_size),
                    schema=schema,
                )
        except (OSError, zipfile.BadZipFile) as exc:
            raise CMSIngestionError(
                f"Unable to read CMS archive {archive_path}: {exc}"
            ) from exc
        if _sha256(archive_path) != original_sha256:
            raise CMSIngestionError(
                f"Source archive changed during ingestion: {archive_path}"
            )
        results.append(result)
    return results
