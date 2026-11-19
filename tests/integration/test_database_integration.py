"""Integration test for the local PostgreSQL service."""

import os

import pytest

from src.database import create_database_engine, verify_database_connection


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

