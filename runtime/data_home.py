import sys

from runtime.storage import data_home as _data_home

sys.modules[__name__] = _data_home
