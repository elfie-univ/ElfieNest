import sys

from runtime.policy import model_route as _model_route

sys.modules[__name__] = _model_route
