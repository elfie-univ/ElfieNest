"""HTTP routes for the isolated interactive Nest Lab."""

from __future__ import annotations

from subprocess import SubprocessError
from typing import Dict, List, Optional, Union

from fastapi import APIRouter, HTTPException

from devtools.nest_lab.actor_creation import ActorSpecies, actor_species
from devtools.nest_lab.models import (
    BedCountRequest,
    CreateActorRequest,
    LabActionRequest,
    LabActor,
    LabEnvironmentState,
    NestLabConflictError,
)
from devtools.nest_lab.preview_build import ensure_preview_bundle
from devtools.nest_lab.world import NestLabWorld

WorldResponse = Dict[str, Union[bool, int, str]]
ActorResponse = Dict[str, Union[str, int, bool]]
EventResponse = Dict[str, Union[str, int]]


def build_router(world: NestLabWorld) -> APIRouter:
    """Build routes bound to one disposable Lab world."""
    router = APIRouter(prefix="/api")

    @router.post("/preview/prepare")
    def prepare_preview() -> dict[str, bool]:
        try:
            ensure_preview_bundle()
        except (RuntimeError, OSError, SubprocessError) as error:
            raise HTTPException(
                status_code=503,
                detail="预览更新失败，已保留上一套资源；请检查服务日志后重试。",
            ) from error
        return {"ready": True}

    @router.get("/environment", response_model=LabEnvironmentState)
    def environment() -> LabEnvironmentState:
        return world.environment()

    @router.get("/actor-species")
    def list_species() -> dict[str, list[ActorSpecies]]:
        return {"items": actor_species()}

    @router.put("/actors/{actor_id}")
    def update_actor(actor_id: str, request: CreateActorRequest) -> ActorResponse:
        try:
            return _actor_response(
                world.update_actor(
                    actor_id,
                    request.species,
                    age_years=request.age_years,
                    gender=request.gender,
                )
            )
        except NestLabConflictError as error:
            raise HTTPException(status_code=409, detail=error.detail) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.delete("/actors/{actor_id}")
    def remove_actor(actor_id: str) -> dict[str, str]:
        try:
            return world.remove_actor(actor_id)
        except NestLabConflictError as error:
            raise HTTPException(status_code=409, detail=error.detail) from error

    @router.get("/action-targets")
    def action_targets() -> dict[str, list[dict[str, Optional[str]]]]:
        return {"items": world.action_targets()}

    @router.post("/actions", status_code=202)
    def execute_action(request: LabActionRequest) -> dict[str, str]:
        try:
            return world.execute_action(request)
        except NestLabConflictError as error:
            raise HTTPException(status_code=409, detail=error.detail) from error

    @router.post("/actors/{actor_id}/stop", status_code=202)
    def stop_action(actor_id: str) -> dict[str, str]:
        try:
            return world.stop_action(actor_id)
        except NestLabConflictError as error:
            raise HTTPException(status_code=409, detail=error.detail) from error

    @router.post("/actors/{actor_id}/prepare-demo", status_code=202)
    def prepare_demonstration(actor_id: str) -> dict[str, str]:
        try:
            return world.prepare_demonstration(actor_id)
        except NestLabConflictError as error:
            raise HTTPException(status_code=409, detail=error.detail) from error

    @router.get("/runtime")
    def runtime_status() -> WorldResponse:
        return world.status()

    @router.get("/world")
    def get_world() -> WorldResponse:
        return world.world()

    @router.put("/world")
    def configure_world(request: BedCountRequest) -> WorldResponse:
        try:
            return world.set_bed_count(request.bed_count)
        except NestLabConflictError as error:
            raise HTTPException(status_code=409, detail=error.detail) from error

    @router.get("/actors")
    def list_actors() -> Dict[str, List[ActorResponse]]:
        return {"items": [_actor_response(actor) for actor in world.actors()]}

    @router.post("/actors/restore-saved")
    def restore_saved_actors() -> Dict[str, List[ActorResponse]]:
        return {
            "items": [_actor_response(actor) for actor in world.restore_saved_actors()]
        }

    @router.post("/actors", status_code=201)
    def create_actor(request: CreateActorRequest) -> ActorResponse:
        try:
            actor = world.add_actor(
                request.species,
                age_years=request.age_years,
                gender=request.gender,
                name=request.name,
            )
        except NestLabConflictError as error:
            raise HTTPException(status_code=409, detail=error.detail) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return _actor_response(actor)

    @router.get("/events")
    def list_events() -> Dict[str, List[EventResponse]]:
        return {"items": list(world.events())}

    @router.post("/simulation/wander")
    def start_wandering() -> Dict[str, bool]:
        return world.set_wandering()

    @router.post("/simulation/pause")
    def pause_simulation() -> Dict[str, bool]:
        return world.pause()

    @router.post("/simulation/resume")
    def resume_simulation() -> Dict[str, bool]:
        return world.resume()

    @router.post("/simulation/reset")
    def reset_simulation() -> Dict[str, int]:
        return world.reset()

    return router


def _actor_response(actor: LabActor) -> ActorResponse:
    return {
        "actor_id": actor.actor_id,
        "species": actor.species,
        "age_years": actor.age_years,
        "gender": actor.gender,
        "name": actor.name,
        "saved": actor.saved,
    }
