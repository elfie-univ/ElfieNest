import sys

from runtime.policy import scene_classifier as _scene_classifier

sys.modules[__name__] = _scene_classifier
