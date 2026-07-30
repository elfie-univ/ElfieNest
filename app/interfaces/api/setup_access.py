"""Local-only access guard for first-time Setup."""

from fastapi import HTTPException, Request

_LOCAL_SETUP_CLIENTS = frozenset({"127.0.0.1", "::1", "testclient"})


def require_local_setup_client(request: Request) -> None:
    client_host = request.client.host if request.client is not None else ""
    if client_host not in _LOCAL_SETUP_CLIENTS:
        raise HTTPException(status_code=403, detail="首次设置仅允许在本机完成")
