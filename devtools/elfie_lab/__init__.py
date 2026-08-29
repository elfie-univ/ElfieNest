"""单精灵开发者调试平台。"""

from typing import Any


def create_app(*args: Any, **kwargs: Any):
    """Load the web composition root only when an app is actually requested."""

    from devtools.elfie_lab.app import create_app as build_app

    return build_app(*args, **kwargs)


__all__ = ["create_app"]
