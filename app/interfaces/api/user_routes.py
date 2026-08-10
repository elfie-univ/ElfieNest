"""普通用户领养流程 REST API。"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.features.accounts import AccountPrincipal
from app.features.adoption.candidates import (
    CandidateSetNotFound,
    create_candidate_set,
    find_candidate,
    get_candidate_set,
    is_accepted_candidate,
    reply_to_candidates,
)
from app.features.adoption.service import (
    AdoptionCapacityError,
    AdoptionRequest,
    AdoptionRuntimeRegistrationError,
    AdoptionValidationError,
    adopt_elfie_for_user,
    adoption_options_for_user,
)
from app.interfaces.api.v1.auth import get_current_user

router = APIRouter(prefix="/api/user", tags=["user"])


@router.get("/adoption-info")
async def adoption_info(
    request: Request,
    user: AccountPrincipal = Depends(get_current_user),  # noqa: B008
):
    """返回领养可选项（物种、性格以及外貌生成方向）。

    性格风格和 species_id 从 ``system.adoption`` 动态读取。
    """
    return adoption_options_for_user(request.app.state.db_path, user_id=user.user_id)


@router.post("/adoption/candidates")
async def adoption_candidates(
    request: Request,
    body: Dict[str, Any],
    user: AccountPrincipal = Depends(get_current_user),  # noqa: B008
):
    """根据同行意向现场生成五位短生命周期候选。"""
    appearance = body.get("appearance")
    answers = body.get("answers")
    if not isinstance(appearance, dict) or not isinstance(answers, list):
        raise HTTPException(status_code=400, detail="缺少完整的外貌倾向或相处答案")
    try:
        snapshot = create_candidate_set(
            user_id=user.user_id,
            species_id=str(body.get("species_id") or ""),
            life_stage=str(body.get("life_stage") or "any"),
            gender=str(body.get("gender") or "any"),
            appearance=appearance,
            answers=[str(answer) for answer in answers],
            db_path=request.app.state.db_path,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {
        "candidate_set_id": snapshot.candidate_set_id,
        "candidates": [candidate.public_dict() for candidate in snapshot.candidates],
    }


@router.post("/adoption/replies")
async def adoption_replies(
    request: Request,
    body: Dict[str, Any],
    user: AccountPrincipal = Depends(get_current_user),  # noqa: B008
):
    """向选中的候选发送认识邀请，并返回双向回信。"""
    candidate_set_id = str(body.get("candidate_set_id") or "")
    raw_ids = body.get("candidate_ids")
    if not candidate_set_id or not isinstance(raw_ids, list):
        raise HTTPException(status_code=400, detail="缺少候选名单或邀请对象")
    try:
        replies = reply_to_candidates(
            candidate_set_id,
            user_id=user.user_id,
            candidate_ids=[str(value) for value in raw_ids],
        )
    except CandidateSetNotFound as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"candidate_set_id": candidate_set_id, "replies": replies}


@router.post("/adoption/commit")
async def commit_adoption(
    request: Request,
    body: Dict[str, Any],
    user: AccountPrincipal = Depends(get_current_user),  # noqa: B008
):
    """把用户最终选中的候选快照一次性落为正式精灵。"""
    candidate_set_id = str(body.get("candidate_set_id") or "")
    candidate_id = str(body.get("candidate_id") or "")
    name = str(body.get("name") or "").strip()
    if not candidate_set_id or not candidate_id:
        raise HTTPException(status_code=400, detail="缺少最终候选")
    try:
        candidate = find_candidate(
            candidate_set_id,
            user_id=user.user_id,
            candidate_id=candidate_id,
        )
        get_candidate_set(candidate_set_id, user_id=user.user_id)
        if not is_accepted_candidate(
            candidate_set_id,
            user_id=user.user_id,
            candidate_id=candidate_id,
        ):
            raise HTTPException(status_code=409, detail="这位候选还没有同意继续认识")
    except CandidateSetNotFound as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from None
    adoption_request = AdoptionRequest(
        name=name,
        species_id=candidate.species_id,
        personality_style=candidate.personality_style,
        height=candidate.height,
        build=candidate.build,
        appearance_overrides=candidate.appearance_overrides,
        appearance_seed=candidate.appearance_seed,
        gender=candidate.gender,
        birth_date=candidate.birth_date,
    )
    try:
        result = adopt_elfie_for_user(
            request.app.state.db_path,
            user_id=user.user_id,
            request=adoption_request,
            engine=getattr(request.app.state, "engine", None),
        )
    except AdoptionValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except AdoptionCapacityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except AdoptionRuntimeRegistrationError:
        raise HTTPException(
            status_code=503, detail="elfie_runtime_unavailable"
        ) from None
    return JSONResponse(
        status_code=201,
        content={
            "elfie_id": result.elfie_id,
            "name": result.name,
            "species_id": result.species_id,
        },
    )
