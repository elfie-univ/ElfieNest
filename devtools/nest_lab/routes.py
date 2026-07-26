"""HTTP routes for the isolated interactive Nest Lab."""

from __future__ import annotations

from typing import Dict, List, Union

from fastapi import APIRouter, HTTPException

from devtools.nest_lab.models import (
    BedCountRequest,
    CreateActorRequest,
    NestLabConflictError,
)
from devtools.nest_lab.world import NestLabWorld

WorldResponse = Dict[str, Union[bool, int, str]]
ActorResponse = Dict[str, str]
EventResponse = Dict[str, Union[str, int]]


def build_router(world: NestLabWorld) -> APIRouter:
    """Build routes bound to one disposable Lab world."""
    router = APIRouter(prefix="/api")

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
        return {
            "items": [
                {"actor_id": actor.actor_id, "species": actor.species}
                for actor in world.actors()
            ]
        }

    @router.post("/actors", status_code=201)
    def create_actor(request: CreateActorRequest) -> ActorResponse:
        try:
            actor = world.add_actor(request.species)
        except NestLabConflictError as error:
            raise HTTPException(status_code=409, detail=error.detail) from error
        return {"actor_id": actor.actor_id, "species": actor.species}

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
