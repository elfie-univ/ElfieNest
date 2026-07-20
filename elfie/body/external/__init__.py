"""母星代理、毛绒玩具和机器人插件共用的外部身体协议。"""

from elfie.body.external.body import ExternalBody
from elfie.body.external.transport import (
    ExternalEventHandler,
    ExternalTransport,
)

__all__ = ["ExternalBody", "ExternalEventHandler", "ExternalTransport"]
