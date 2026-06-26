import sys

from runtime.providers import ollama as _ollama

sys.modules[__name__] = _ollama
