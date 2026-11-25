"""Shared application logging configuration."""

from __future__ import annotations

import logging
import os


def configure_logging(level: str | None = None) -> None:
    """Configure concise timestamped logs for command-line pipeline processes."""
    selected_level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    numeric_level = getattr(logging, selected_level, None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid logging level: {selected_level}")
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)sZ %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        force=True,
    )
    logging.Formatter.converter = __import__("time").gmtime
