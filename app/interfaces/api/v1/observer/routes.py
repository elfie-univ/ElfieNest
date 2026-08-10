"""Versioned HTTP boundary for scoped Observer sessions."""

from __future__ import annotations

from typing import Optional, Union, cast

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import JSONResponse, Response

from app.features.accounts import AccountPrincipal
from app.interfaces.api.v1.auth import get_current_user
from app.orchestration.observer import (
    NextObserverFrameQuery,
    ObserverDeltaResult,
    ObserverEntityRecord,
    ObserverError,
    ObserverFacade,
    ObserverForbidden,
    ObserverPrincipal,
    ObserverRateLimited,
    ObserverSnapshotResult,
    ObserverSubscription,
    ObserverUnavailable,
    ObserverWorldIntent,
    OpenObserverSessionCommand,
    SubmitObserverIntentCommand,
    UpdateObserverInterestCommand,
    session_token_fingerprint,
)

from .models import (
    ObserverDeltaResponse,
    ObserverEntityPatchResponse,
    ObserverEntityResponse,
    ObserverErrorDetails,
    ObserverErrorItem,
    ObserverErrorResponse,
    ObserverFrameResponse,
    ObserverIntentAcceptedResponse,
    ObserverIntentRequest,
    ObserverInterestRequest,
    ObserverSnapshotResponse,
    ObserverSubscriptionRequest,
    ObserverSubscriptionResponse,
    OpenObserverSessionRequest,
    OpenObserverSessionResponse,
)

router = APIRouter(prefix="/api/v1/observer", tags=["observer"])
CurrentPrincipal = Depends(get_current_user)
ObserverCapability = Header(..., alias="X-ElfieNest-Observer-Capability")


@router.post(
    "/sessions",
    response_model=OpenObserverSessionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        403: {"model": ObserverErrorResponse},
        503: {"model": ObserverErrorResponse},
    },
)
def open_observer_session(
    payload: OpenObserverSessionRequest,
    request: Request,
    principal: AccountPrincipal = CurrentPrincipal,
) -> Union[OpenObserverSessionResponse, JSONResponse]:
    try:
        result = _facade(request).open_session(
            OpenObserverSessionCommand(
                principal=_principal(principal),
                session_fingerprint=_session_fingerprint(request, principal),
                subscription=_subscription(payload.subscription),
            )
        )
    except ObserverError as error:
        return _error_response(error)
    return OpenObserverSessionResponse(capability=result.capability)


@router.post(
    "/intents",
    response_model=ObserverIntentAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        403: {"model": ObserverErrorResponse},
        429: {"model": ObserverErrorResponse},
        503: {"model": ObserverErrorResponse},
    },
)
def submit_observer_intent(
    payload: ObserverIntentRequest,
    request: Request,
    capability: str = ObserverCapability,
    principal: AccountPrincipal = CurrentPrincipal,
) -> Union[ObserverIntentAcceptedResponse, JSONResponse]:
    try:
        _facade(request).submit_intent(
            SubmitObserverIntentCommand(
                principal=_principal(principal),
                session_fingerprint=_session_fingerprint(request, principal),
                capability=capability,
                intent=ObserverWorldIntent(
                    actor_id=payload.actor_id,
                    interaction=payload.interaction,
                ),
            )
        )
    except ObserverError as error:
        return _error_response(error)
    return ObserverIntentAcceptedResponse(detail="observer intent accepted")


@router.put(
    "/interest",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    responses={
        403: {"model": ObserverErrorResponse},
        503: {"model": ObserverErrorResponse},
    },
)
def update_observer_interest(
    payload: ObserverInterestRequest,
    request: Request,
    capability: str = ObserverCapability,
    principal: AccountPrincipal = CurrentPrincipal,
) -> Response:
    try:
        _facade(request).update_interest(
            UpdateObserverInterestCommand(
                principal=_principal(principal),
                session_fingerprint=_session_fingerprint(request, principal),
                capability=capability,
                subscription=_subscription(payload.subscription),
                visible_entity_ids=payload.visible_entity_ids,
            )
        )
    except ObserverError as error:
        return _error_response(error)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/frames",
    response_model=Optional[ObserverFrameResponse],
    response_model_exclude_unset=True,
    responses={
        403: {"model": ObserverErrorResponse},
        503: {"model": ObserverErrorResponse},
    },
)
def next_observer_frame(
    request: Request,
    capability: str = ObserverCapability,
    acknowledged_generation: Optional[int] = None,
    acknowledged_sequence: Optional[int] = None,
    principal: AccountPrincipal = CurrentPrincipal,
) -> Union[ObserverSnapshotResponse, ObserverDeltaResponse, None, JSONResponse]:
    try:
        result = _facade(request).next_frame(
            NextObserverFrameQuery(
                principal=_principal(principal),
                session_fingerprint=_session_fingerprint(request, principal),
                capability=capability,
                acknowledged_generation=acknowledged_generation,
                acknowledged_sequence=acknowledged_sequence,
            )
        )
    except ObserverError as error:
        return _error_response(error)
    if result is None:
        return None
    if isinstance(result, ObserverSnapshotResult):
        return ObserverSnapshotResponse(
            protocol=3,
            kind="snapshot",
            generation=result.generation,
            sequence=result.sequence,
            scope=_subscription_response(result.scope),
            entities={
                projected.state.entity_id: _entity_response(projected.state)
                for projected in result.entities
            },
            entity_revisions={
                projected.state.entity_id: projected.revision
                for projected in result.entities
            },
        )
    delta = cast(ObserverDeltaResult, result)
    return ObserverDeltaResponse(
        protocol=3,
        kind="delta",
        generation=delta.generation,
        sequence=delta.sequence,
        scope=_subscription_response(delta.scope),
        entity_id=delta.entity_id,
        entity_revision=delta.entity_revision,
        patch=ObserverEntityPatchResponse.model_validate(
            {change.field: change.value for change in delta.changes}
        ),
    )


def _facade(request: Request) -> ObserverFacade:
    facade = getattr(request.app.state, "observer", None)
    if not isinstance(facade, ObserverFacade):
        raise ObserverUnavailable("Observer service unavailable")
    return facade


def _principal(principal: AccountPrincipal) -> ObserverPrincipal:
    if principal.role in {"owner", "admin"}:
        return ObserverPrincipal(user_id=principal.user_id, access="manager")
    if principal.role == "user":
        return ObserverPrincipal(user_id=principal.user_id, access="member")
    raise ObserverForbidden("unsupported Observer role")


def _session_fingerprint(request: Request, principal: AccountPrincipal) -> str:
    del principal
    raw_token = request.cookies.get("session_token", "")
    token = raw_token if isinstance(raw_token, str) else ""
    return cast(str, session_token_fingerprint(token))


def _subscription(payload: ObserverSubscriptionRequest) -> ObserverSubscription:
    return ObserverSubscription(
        kind=payload.kind,
        room_id=payload.room_id,
        elfie_id=payload.elfie_id,
    )


def _subscription_response(
    subscription: ObserverSubscription,
) -> ObserverSubscriptionResponse:
    return ObserverSubscriptionResponse(
        kind=subscription.kind,
        room_id=subscription.room_id,
        elfie_id=subscription.elfie_id,
    )


def _entity_response(entity: ObserverEntityRecord) -> ObserverEntityResponse:
    return ObserverEntityResponse(
        room_id=entity.room_id,
        zone_id=entity.zone_id,
        posture=entity.posture,
        active=entity.active,
        active_command_id=entity.active_command_id,
        species_id=entity.species_id,
        appearance=dict(entity.appearance),
        home_anchor_id=entity.home_anchor_id,
    )


def _error_response(error: ObserverError) -> JSONResponse:
    status_code = 503
    code = "observer_unavailable"
    if isinstance(error, ObserverForbidden):
        status_code = 403
        code = "observer_forbidden"
    elif isinstance(error, ObserverRateLimited):
        status_code = 429
        code = "observer_rate_limited"
    body = ObserverErrorResponse(
        error=ObserverErrorItem(
            code=code,
            message=str(error),
            details=ObserverErrorDetails(),
        )
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


__all__ = ("router",)
