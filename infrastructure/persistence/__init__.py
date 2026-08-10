"""SQLite adapters and shared connection policy."""

from .accounts import SessionRepository, SQLiteAccountsAdapter, hash_session_token
from .adoption import SQLiteAdoptionAdapter
from .adoption_profiles import FinalElfieWorkspaceAdapter
from .bodies import SQLiteBodiesAdapter
from .elfies import SQLiteElfiesProjectionAdapter
from .embodiment import SQLiteEmbodimentLeaseAdapter
from .food import SQLiteFoodAdapter
from .nest_management import SQLiteNestManagementAdapter
from .operations import SQLiteOperationsAdapter

__all__ = (
    "FinalElfieWorkspaceAdapter",
    "SQLiteAccountsAdapter",
    "SQLiteAdoptionAdapter",
    "SQLiteBodiesAdapter",
    "SQLiteElfiesProjectionAdapter",
    "SQLiteEmbodimentLeaseAdapter",
    "SQLiteFoodAdapter",
    "SQLiteNestManagementAdapter",
    "SQLiteOperationsAdapter",
    "SessionRepository",
    "hash_session_token",
)
