"""Authenticated, capability-scoped Observer session endpoints."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.features.accounts.auth import (
    get_current_user,
    get_session_ttl_seconds,
    verify_session,
)
from app.infrastructure.persistence.interface_query_repository import (
    InterfaceQueryRepository,
)
from nest.godot_gateway.observer import (
    ObserverHello,
    ObserverInterest,
    ObserverSemanticEntity,
    ObserverSnapshot,
    ViewerPrincipal,
    WorldChangingIntent,
)
from nest.godot_gateway.observer_sessions import (
    ObserverAuthorizationError,
    ObserverBackpressureError,
    ObserverSessionRegistry,
)

router = APIRouter(prefix="/api/observer", tags=["observer"])


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def open_observer_session(
    hello: ObserverHello,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Dict[str, str]:
    """Issue an opaque Observer capability for the existing authenticated session."""
    try:
        capability = _registry(request).open_session(
            _principal(user),
            _session_fingerprint(request, user),
            hello.subscription,
            expires_at=time.time() + get_session_ttl_seconds(request.app.state.db_path),
        )
    except ObserverAuthorizationError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    return {"capability": capability}


@router.post("/intents", status_code=status.HTTP_202_ACCEPTED)
async def submit_observer_intent(
    intent: WorldChangingIntent,
    request: Request,
    capability: str = Header(..., alias="X-ElfieNest-Observer-Capability"),
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Dict[str, str]:
    """Authorize one high-level interaction before it can reach a world sink."""
    try:
        _registry(request).submit_world_intent(
            _principal(user),
            _session_fingerprint(request, user),
            capability,
            intent,
            now=time.time(),
        )
    except ObserverBackpressureError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    except ObserverAuthorizationError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    return {"detail": "observer intent accepted"}


@router.put("/interest", status_code=status.HTTP_204_NO_CONTENT)
async def update_observer_interest(
    interest: ObserverInterest,
    request: Request,
    capability: str = Header(..., alias="X-ElfieNest-Observer-Capability"),
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> None:
    """Replace an Observer's reduced interest scope and require a snapshot."""
    try:
        _registry(request).update_interest(
            _principal(user),
            _session_fingerprint(request, user),
            capability,
            interest,
            now=time.time(),
        )
    except ObserverAuthorizationError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error


@router.get("/frames")
async def next_observer_frame(
    request: Request,
    capability: str = Header(..., alias="X-ElfieNest-Observer-Capability"),
    acknowledged_generation: Optional[int] = None,
    acknowledged_sequence: Optional[int] = None,
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Optional[Dict[str, Any]]:
    """Poll one ordered scoped frame; a stale cursor is replaced by a snapshot."""
    try:
        frame = _registry(request).next_projection(
            _principal(user),
            _session_fingerprint(request, user),
            capability,
            acknowledged_generation=acknowledged_generation,
            acknowledged_sequence=acknowledged_sequence,
            now=time.time(),
        )
    except ObserverAuthorizationError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    if frame is None:
        return None
    if isinstance(frame, ObserverSnapshot):
        return frame.model_dump(mode="json")
    payload = frame.model_dump(mode="json")
    payload["patch"] = frame.patch.model_dump(mode="json", exclude_unset=True)
    return payload


def _registry(request: Request) -> ObserverSessionRegistry:
    existing = getattr(request.app.state, "observer_sessions", None)
    if isinstance(existing, ObserverSessionRegistry):
        return existing

    registry = ObserverSessionRegistry(
        owns_elfie=lambda user_id, elfie_id: _owns_elfie(
            request.app.state.db_path,
            user_id,
            elfie_id,
        ),
        submit_intent=lambda intent: _sink(request)(intent),
        semantic_entities=lambda: _semantic_entities(request),
    )
    request.app.state.observer_sessions = registry
    return registry


def _principal(user: Dict[str, Any]) -> ViewerPrincipal:
    role = user.get("role")
    if role in {"owner", "admin"}:
        return ViewerPrincipal(user_id=user["user_id"], role="owner")
    if role == "user":
        return ViewerPrincipal(user_id=user["user_id"], role="user")
    raise HTTPException(status_code=403, detail="unsupported Observer role")


def _session_fingerprint(request: Request, user: Dict[str, Any]) -> str:
    """Revalidate the existing login and retain only a non-reversible token digest."""
    token = request.cookies.get("session_token", "")
    verified = verify_session(token, request.app.state.db_path)
    if verified is None or verified["user_id"] != user["user_id"]:
        raise HTTPException(status_code=401, detail="会话无效或已过期")
    return session_token_fingerprint(token)


def _owns_elfie(db_path: str, user_id: int, elfie_id: str) -> bool:
    return (
        InterfaceQueryRepository(db_path).get_elfie(elfie_id, owner_user_id=user_id)
        is not None
    )


def _sink(request: Request) -> Callable[[WorldChangingIntent], None]:
    sink = getattr(request.app.state, "observer_intent_sink", None)
    if not callable(sink):
        raise ObserverAuthorizationError("observer world intent sink is unavailable")
    return sink


def _semantic_entities(request: Request) -> Dict[str, ObserverSemanticEntity]:
    """Read a tested semantic projection provider without accepting geometry."""
    provider = getattr(request.app.state, "observer_semantic_entities", None)
    if callable(provider):
        raw = provider()
        if isinstance(raw, dict):
            return {
                entity_id: ObserverSemanticEntity.model_validate(entity)
                for entity_id, entity in raw.items()
            }
    engine = request.app.state.engine
    session = getattr(engine, "session", None)
    projection = getattr(session, "observer_semantic_entities", None)
    if callable(projection):
        return projection()
    return {}


def session_token_fingerprint(token: str) -> str:
    """Derive the session binding without exposing or storing the raw cookie token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
