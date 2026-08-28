"""Infrastructure persistence Adapters for Elfie semantic memory."""

from .migration import MigrationReport, import_legacy_database
from .sqlite_memory_store import (
    EpisodeIdempotencyError,
    MemoryStoreMigrationRequired,
    MemoryStorePathError,
    MemoryStoreSchemaError,
    SQLiteMemoryStoreAdapter,
)

__all__ = (
    "EpisodeIdempotencyError",
    "MemoryStoreMigrationRequired",
    "MemoryStorePathError",
    "MemoryStoreSchemaError",
    "MigrationReport",
    "SQLiteMemoryStoreAdapter",
    "import_legacy_database",
)
