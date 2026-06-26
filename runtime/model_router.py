import sys

from runtime.policy import router as _router

sys.modules[__name__] = _router
