"""Integration test for the local PostgreSQL service."""

import os
import csv
import uuid
from datetime import date
from pathlib import Path

import pytest
import pandas as pd
from sqlalchemy import text

from src.database import (
    create_database_engine,
    database_transaction,
    verify_database_connection,
)
from src.ingestion.synthea_loader import EXPECTED_HEADERS, load_synthea_csv
from src.ingestion.cms_loader import CMS_SOURCES, _load_reference


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DATABASE_INTEGRATION_TESTS") != "1",
    reason="Set RUN_DATABASE_INTEGRATION_TESTS=1 with database variables configured.",
)


def test_database_and_required_schemas_are_available() -> None:
    engine = create_database_engine()
    try:
        result = verify_database_connection(engine)
    finally:
        engine.dispose()

    assert result["database_name"] == os.environ["POSTGRES_DB"]
    assert result["schemas"] == ["analytics", "raw", "staging"]


def test_synthea_csv_loads_and_reconciles_in_postgresql(tmp_path: Path) -> None:
    schema = f"test_ingestion_{uuid.uuid4().hex[:12]}"
    csv_path = tmp_path / "patients.csv"
    first_row = ["" for _ in EXPECTED_HEADERS["patients.csv"]]
    first_row[0] = "001"
    first_row[1] = "1980-01-01"
    first_row[12] = "NA"
    with csv_path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target, lineterminator="\n")
        writer.writerow(EXPECTED_HEADERS["patients.csv"])
        writer.writerow(first_row)

    engine = create_database_engine()
    try:
        with database_transaction(engine) as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        result = load_synthea_csv(engine, csv_path, schema=schema, chunk_size=1)
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    f'SELECT "Id", "DEATHDATE", "RACE", '
                    f'_source_filename, _source_row_number FROM "{schema}".patients'
                )
            ).one()
        assert result.source_row_count == 1
        assert result.loaded_row_count == 1
        assert result.difference == 0
        assert row == ("001", None, "NA", "patients.csv", 1)
    finally:
        with database_transaction(engine) as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def test_cms_reference_loads_and_reconciles_in_postgresql() -> None:
    schema = f"test_cms_ingestion_{uuid.uuid4().hex[:12]}"
    source = CMS_SOURCES[0]
    frame = pd.DataFrame(
        [{
            "code": "A000",
            "description": "Synthetic parser test description",
            "raw_record": "A000    Synthetic parser test description",
            "_source_row_number": 1,
        }]
    )
    engine = create_database_engine()
    try:
        with database_transaction(engine) as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        result = _load_reference(
            engine,
            source,
            "cms_icd10cm_test",
            "test-member.txt",
            [frame],
            schema=schema,
        )
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    f'SELECT code, _effective_start, _effective_end '
                    f'FROM "{schema}".cms_icd10cm_test'
                )
            ).one()
        assert result.source_row_count == result.loaded_row_count == 1
        assert result.difference == 0
        assert row == (
            "A000",
            date.fromisoformat(source.effective_start),
            date.fromisoformat(source.effective_end),
        )
    finally:
        with database_transaction(engine) as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()

