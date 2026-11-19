"""Unit tests for environment-driven database configuration."""

import pytest

from src.database.connection import (
    DatabaseConfigurationError,
    DatabaseSettings,
    create_database_engine,
)


def valid_environment() -> dict[str, str]:
    """Return a complete test-only environment mapping."""
    return {
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "healthcare_revenue_cycle",
        "POSTGRES_USER": "healthcare_app",
        "POSTGRES_PASSWORD": "local:p@ss/word",
    }


def test_settings_are_loaded_and_typed() -> None:
    settings = DatabaseSettings.from_environment(valid_environment())

    assert settings.host == "localhost"
    assert settings.port == 5432
    assert settings.pool_size == 5
    assert settings.echo is False


def test_sqlalchemy_url_handles_special_characters_in_password() -> None:
    settings = DatabaseSettings.from_environment(valid_environment())

    url = settings.sqlalchemy_url()

    assert url.password == "local:p@ss/word"
    assert "local%3Ap%40ss%2Fword" in url.render_as_string(hide_password=False)


def test_missing_password_is_rejected() -> None:
    environment = valid_environment()
    del environment["POSTGRES_PASSWORD"]

    with pytest.raises(DatabaseConfigurationError, match="POSTGRES_PASSWORD"):
        DatabaseSettings.from_environment(environment)


@pytest.mark.parametrize("port", ["not-a-number", "0", "-1"])
def test_invalid_port_is_rejected(port: str) -> None:
    environment = valid_environment()
    environment["POSTGRES_PORT"] = port

    with pytest.raises(DatabaseConfigurationError, match="POSTGRES_PORT"):
        DatabaseSettings.from_environment(environment)


def test_invalid_boolean_is_rejected() -> None:
    environment = valid_environment()
    environment["DB_ECHO"] = "sometimes"

    with pytest.raises(DatabaseConfigurationError, match="DB_ECHO"):
        DatabaseSettings.from_environment(environment)


def test_engine_uses_psycopg_and_pool_pre_ping() -> None:
    settings = DatabaseSettings.from_environment(valid_environment())

    engine = create_database_engine(settings)
    try:
        assert engine.dialect.driver == "psycopg"
        assert engine.pool._pre_ping is True
    finally:
        engine.dispose()

