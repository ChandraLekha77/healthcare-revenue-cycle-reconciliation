"""Unit tests for CMS archive acquisition and validation."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest
import pandas as pd

from src.ingestion.cms_loader import (
    CMS_SOURCES,
    HCPCS_COLUMNS,
    HCPCS_MEMBER,
    ICD10_MEMBER,
    MPFS_COLUMNS,
    MPFS_MEMBER,
    CMSValidationError,
    _hcpcs_chunks,
    _icd10_chunks,
    _mpfs_chunks,
    acquire_cms_data,
    validate_archive,
)


def build_test_archive(path: Path, required_member: str) -> str:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(required_member, "format documentation only\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_validate_archive_records_members(tmp_path: Path) -> None:
    archive_path = tmp_path / "cms.zip"
    member_name = "layout.txt"
    archive_hash = build_test_archive(archive_path, member_name)
    source = replace(
        CMS_SOURCES[0],
        filename=archive_path.name,
        sha256=archive_hash,
        required_members=(member_name,),
    )

    metadata = validate_archive(archive_path, source)

    assert metadata.member_count == 1
    assert metadata.members[0]["filename"] == member_name


def test_validate_archive_rejects_checksum_mismatch(tmp_path: Path) -> None:
    archive_path = tmp_path / "cms.zip"
    build_test_archive(archive_path, "layout.txt")
    source = replace(
        CMS_SOURCES[0],
        filename=archive_path.name,
        sha256="0" * 64,
        required_members=("layout.txt",),
    )

    with pytest.raises(CMSValidationError, match="Checksum mismatch"):
        validate_archive(archive_path, source)


def test_acquisition_is_repeatable_and_writes_inventory(tmp_path: Path) -> None:
    archive_path = tmp_path / "source.zip"
    member_name = "layout.txt"
    archive_hash = build_test_archive(archive_path, member_name)
    source = replace(
        CMS_SOURCES[0],
        filename="preserved-source.zip",
        source_url=archive_path.as_uri(),
        sha256=archive_hash,
        required_members=(member_name,),
    )
    output_directory = tmp_path / "raw"

    first = acquire_cms_data(output_directory, sources=(source,))
    second = acquire_cms_data(output_directory, sources=(source,))

    assert first[0].sha256 == second[0].sha256 == archive_hash
    inventory = json.loads(
        (output_directory / "_inventory.json").read_text(encoding="utf-8")
    )
    assert inventory["datasets"][0]["source_url"] == archive_path.as_uri()
    assert inventory["datasets"][0]["members"][0]["filename"] == member_name


def test_icd10_fixed_width_parser_retains_raw_record(tmp_path: Path) -> None:
    archive_path = tmp_path / "icd.zip"
    raw_record = "A000    Cholera due to Vibrio cholerae"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(ICD10_MEMBER, raw_record + "\n")

    with zipfile.ZipFile(archive_path) as archive:
        parsed = pd.concat(_icd10_chunks(archive, chunk_size=1), ignore_index=True)

    assert parsed.iloc[0].to_dict() == {
        "code": "A000",
        "description": "Cholera due to Vibrio cholerae",
        "raw_record": raw_record,
        "_source_row_number": 1,
    }


def test_hcpcs_workbook_parser_retains_all_fields_and_code_padding(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "hcpcs.zip"
    row = {column: "" for column in HCPCS_COLUMNS}
    row.update({"HCPC": "   A1", "LONG DESCRIPTION": "Dressing", "ACT EFF DT": "20020701"})
    workbook = io.BytesIO()
    pd.DataFrame([row]).to_excel(workbook, index=False, engine="openpyxl")
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(HCPCS_MEMBER, workbook.getvalue())

    with zipfile.ZipFile(archive_path) as archive:
        parsed = pd.concat(_hcpcs_chunks(archive, chunk_size=1), ignore_index=True)

    assert len(parsed.columns) == len(HCPCS_COLUMNS) + 1
    assert parsed.loc[0, "hcpcs_code"] == "   A1"
    assert parsed.loc[0, "action_effective_date"] == "20020701"
    assert parsed.loc[0, "_source_row_number"] == 2


def test_mpfs_parser_skips_published_header_and_preserves_values(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "mpfs.zip"
    header = "\n".join(["header"] * 10)
    values = ["" for _ in MPFS_COLUMNS]
    values[0] = "00100"
    values[2] = "Anesthesia service"
    values[25] = "33.4009"
    content = header + "\n" + ",".join(values) + "\n"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(MPFS_MEMBER, content)

    with zipfile.ZipFile(archive_path) as archive:
        parsed = pd.concat(_mpfs_chunks(archive, chunk_size=1), ignore_index=True)

    assert parsed.loc[0, "hcpcs_code"] == "00100"
    assert parsed.loc[0, "conversion_factor"] == "33.4009"
    assert parsed.loc[0, "_source_row_number"] == 11
