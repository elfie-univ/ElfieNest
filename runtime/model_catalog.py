import sys

from runtime.models import catalog as _catalog

sys.modules[__name__] = _catalog
