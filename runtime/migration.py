import sys

from runtime.storage import migration as _migration

sys.modules[__name__] = _migration
