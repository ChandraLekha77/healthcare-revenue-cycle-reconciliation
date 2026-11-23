"""Acquire and validate version-pinned CMS reference data archives."""

from __future__ import annotations

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
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Final, Sequence

LOGGER = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIRECTORY: Final = Path("data/raw/cms")
DEFAULT_INVENTORY_FILENAME: Final = "_inventory.json"
DOWNLOAD_CHUNK_SIZE: Final = 1024 * 1024


class CMSAcquisitionError(RuntimeError):
    """Raised when an official CMS archive cannot be safely acquired."""


class CMSValidationError(ValueError):
    """Raised when a local CMS archive fails structural validation."""


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
