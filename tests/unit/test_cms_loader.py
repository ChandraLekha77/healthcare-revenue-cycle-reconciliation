"""Unit tests for CMS archive acquisition and validation."""

from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from src.ingestion.cms_loader import (
    CMS_SOURCES,
    CMSValidationError,
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
