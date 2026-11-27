"""Source-data acquisition and ingestion utilities."""

from src.ingestion.cms_loader import (
    CMS_SOURCES,
    CMSAcquisitionError,
    CMSArchiveMetadata,
    CMSSource,
    CMSValidationError,
    acquire_cms_data,
    validate_cms_directory,
)
from src.ingestion.synthea_loader import (
    EXPECTED_HEADERS,
    FileMetadata,
    SyntheaAcquisitionError,
    SyntheaValidationError,
    acquire_synthea_data,
    validate_synthea_directory,
    write_inventory,
)
from src.ingestion.cms_loader import (
    CMSIngestionError,
    CMSIngestionResult,
    load_cms_references,
)

__all__ = [
    "CMS_SOURCES",
    "CMSAcquisitionError",
    "CMSArchiveMetadata",
    "CMSSource",
    "CMSValidationError",
    "EXPECTED_HEADERS",
    "FileMetadata",
    "SyntheaAcquisitionError",
    "SyntheaValidationError",
    "acquire_synthea_data",
    "acquire_cms_data",
    "validate_cms_directory",
    "validate_synthea_directory",
    "write_inventory",
]
"""Source acquisition and raw ingestion interfaces."""

from src.ingestion.synthea_loader import (
    IngestionResult,
    SyntheaIngestionError,
    load_synthea_csv,
    load_synthea_directory,
)

__all__ = [
    "IngestionResult",
    "SyntheaIngestionError",
    "load_synthea_csv",
    "load_synthea_directory",
    "CMSIngestionError",
    "CMSIngestionResult",
    "load_cms_references",
]
