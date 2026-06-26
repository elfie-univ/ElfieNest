import sys

from runtime.providers import profiles as _profiles

sys.modules[__name__] = _profiles
