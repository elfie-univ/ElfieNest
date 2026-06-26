import sys

from runtime.models import registry as _registry

sys.modules[__name__] = _registry
