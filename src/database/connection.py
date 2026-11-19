"""Environment-driven SQLAlchemy connection management for PostgreSQL."""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Mapping

from sqlalchemy import Connection, Engine, URL, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

LOGGER = logging.getLogger(__name__)


class DatabaseConfigurationError(ValueError):
    """Raised when required database configuration is missing or invalid."""


class DatabaseConnectionError(RuntimeError):
    """Raised when a database operation cannot establish a connection."""


def _required(environment: Mapping[str, str], name: str) -> str:
    """Return a non-empty required environment value."""
    value = environment.get(name, "").strip()
    if not value:
        raise DatabaseConfigurationError(
            f"Required environment variable {name} is not set."
        )
    return value


def _integer(
    environment: Mapping[str, str], name: str, default: int, minimum: int = 0
) -> int:
    """Parse and validate an integer environment value."""
    raw_value = environment.get(name, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise DatabaseConfigurationError(
            f"Environment variable {name} must be an integer."
        ) from exc
    if value < minimum:
        raise DatabaseConfigurationError(
            f"Environment variable {name} must be at least {minimum}."
        )
    return value


def _boolean(environment: Mapping[str, str], name: str, default: bool) -> bool:
    """Parse a strict boolean environment value."""
    raw_value = environment.get(name, str(default)).strip().lower()
    if raw_value in {"1", "true", "yes", "on"}:
        return True
    if raw_value in {"0", "false", "no", "off"}:
        return False
    raise DatabaseConfigurationError(
        f"Environment variable {name} must be a boolean value."
    )


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    """Validated database settings loaded from environment variables."""

    host: str
    port: int
    database: str
    username: str
    password: str
    echo: bool = False
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> "DatabaseSettings":
        """Build settings from a supplied mapping or the process environment."""
        values = os.environ if environment is None else environment
        return cls(
            host=_required(values, "POSTGRES_HOST"),
            port=_integer(values, "POSTGRES_PORT", 5432, minimum=1),
            database=_required(values, "POSTGRES_DB"),
            username=_required(values, "POSTGRES_USER"),
            password=_required(values, "POSTGRES_PASSWORD"),
            echo=_boolean(values, "DB_ECHO", False),
            pool_size=_integer(values, "DB_POOL_SIZE", 5, minimum=1),
            max_overflow=_integer(values, "DB_MAX_OVERFLOW", 10),
            pool_timeout=_integer(values, "DB_POOL_TIMEOUT", 30, minimum=1),
        )

    def sqlalchemy_url(self) -> URL:
        """Create a SQLAlchemy URL without manually interpolating credentials."""
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.username,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.database,
        )


def create_database_engine(settings: DatabaseSettings | None = None) -> Engine:
    """Create a reusable, pool-enabled SQLAlchemy engine."""
    database_settings = settings or DatabaseSettings.from_environment()
    return create_engine(
        database_settings.sqlalchemy_url(),
        echo=database_settings.echo,
        pool_pre_ping=True,
        pool_size=database_settings.pool_size,
        max_overflow=database_settings.max_overflow,
        pool_timeout=database_settings.pool_timeout,
    )


@contextmanager
def database_connection(engine: Engine) -> Iterator[Connection]:
    """Yield a connection and convert driver errors into a domain exception."""
    try:
        with engine.connect() as connection:
            yield connection
    except SQLAlchemyError as exc:
        LOGGER.exception("Database connection operation failed.")
        raise DatabaseConnectionError("Database connection operation failed.") from exc


@contextmanager
def database_transaction(engine: Engine) -> Iterator[Connection]:
    """Yield a transactional connection that commits or rolls back atomically."""
    try:
        with engine.begin() as connection:
            yield connection
    except SQLAlchemyError as exc:
        LOGGER.exception("Database transaction failed and was rolled back.")
        raise DatabaseConnectionError("Database transaction failed.") from exc


def verify_database_connection(engine: Engine) -> dict[str, Any]:
    """Verify connectivity and return the database and required schema names."""
    query = text(
        """
        SELECT current_database() AS database_name,
               schema_name
        FROM information_schema.schemata
        WHERE schema_name IN ('raw', 'staging', 'analytics')
        ORDER BY schema_name
        """
    )
    with database_connection(engine) as connection:
        rows = connection.execute(query).mappings().all()

    schemas = [row["schema_name"] for row in rows]
    missing_schemas = sorted({"raw", "staging", "analytics"} - set(schemas))
    if missing_schemas:
        raise DatabaseConnectionError(
            "Database is reachable but required schemas are missing: "
            + ", ".join(missing_schemas)
        )

    LOGGER.info("Database connectivity and required schemas verified.")
    return {"database_name": rows[0]["database_name"], "schemas": schemas}
