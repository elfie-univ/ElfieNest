"""SQLite adapters and shared connection policy."""

from .accounts import SessionRepository, SQLiteAccountsAdapter, hash_session_token
from .adoption import SQLiteAdoptionAdapter
from .adoption_profiles import FinalElfieWorkspaceAdapter
from .bodies import SQLiteBodiesAdapter
from .elfies import SQLiteElfiesProjectionAdapter
from .embodiment import SQLiteEmbodimentLeaseAdapter
from .final_schema import create_final_nest_database
from .food import SQLiteFoodAdapter
from .nest_management import SQLiteNestManagementAdapter
from .nest_state import SQLiteNestStateAdapter
from .operations import SQLiteOperationsAdapter
from .store import LegacyDataRootError, get_db, init_db

__all__ = (
    "FinalElfieWorkspaceAdapter",
    "LegacyDataRootError",
    "SQLiteAccountsAdapter",
    "SQLiteAdoptionAdapter",
    "SQLiteBodiesAdapter",
    "SQLiteElfiesProjectionAdapter",
    "SQLiteEmbodimentLeaseAdapter",
    "SQLiteFoodAdapter",
    "SQLiteNestManagementAdapter",
    "SQLiteNestStateAdapter",
    "SQLiteOperationsAdapter",
    "SessionRepository",
    "create_final_nest_database",
    "get_db",
    "hash_session_token",
    "init_db",
)
