import sys

from runtime.usage import token_tracker as _token_tracker

sys.modules[__name__] = _token_tracker
