import sys

from runtime.safety import permissions as _permissions

sys.modules[__name__] = _permissions
