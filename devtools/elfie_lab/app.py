"""独立的本地 Web 服务，不依赖 ElfieNestEngine。"""

from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from devtools.elfie_lab.schemas import StimulusBundle
from devtools.elfie_lab.session import SessionRegistry
from devtools.elfie_lab.storage import ElfieLabStorage
from devtools.runtime_lab import RuntimeLabConfigStore


class CreateElfieRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    anatomy_type: str = "biped"
    description: str = Field(default="", max_length=240)


class TurnRequest(BaseModel):
    message: str = Field(default="", max_length=8000)
    mode: str = "mock"
    temperature: float = Field(default=24.0, ge=-50.0, le=100.0)
    is_network_online: bool = True
    salience_score: float = Field(default=20.0, ge=0.0, le=100.0)
    impact_force: float = Field(default=0.0, ge=0.0, le=1000.0)
    impact_direction: str = Field(default="none", max_length=40)
    gentle_stroke: float = Field(default=0.0, ge=0.0, le=100.0)
    state_injection: Dict[str, Any] = Field(default_factory=dict)


def create_app(
    data_dir: Optional[str] = None, runtime_config_dir: Optional[str] = None
) -> FastAPI:
    app = FastAPI(
        title="Elfie Lab",
        description="单精灵开发者调试平台",
        docs_url="/api/docs",
        redoc_url=None,
    )
    storage = ElfieLabStorage(data_dir)
    if runtime_config_dir is None and data_dir is not None:
        runtime_config_dir = str(Path(data_dir) / "runtime_config")
    runtime_store = RuntimeLabConfigStore(runtime_config_dir)
    sessions = SessionRegistry(storage, str(runtime_store.root))
    static_dir = Path(__file__).with_name("static")
    app.state.storage = storage
    app.state.sessions = sessions
    app.state.runtime_store = runtime_store
    app.mount("/static", StaticFiles(directory=static_dir), name="elfie_lab_static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(static_dir / "index.html")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "service": "elfie-lab"}

    @app.get("/api/runtime/status")
    def runtime_status():
        return runtime_store.status()

    @app.get("/api/elfies")
    def list_elfies():
        return {"items": [item.to_dict() for item in storage.list_elfies()]}

    @app.post("/api/elfies", status_code=201)
    def create_elfie(request: CreateElfieRequest):
        try:
            spec = storage.create_elfie(
                request.name, request.anatomy_type, request.description
            )
            return sessions.get(spec.elfie_id).get_payload()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/elfies/{elfie_id}")
    def get_elfie(elfie_id: str):
        try:
            return sessions.get(elfie_id).get_payload()
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/elfies/{elfie_id}/turns")
    def create_turn(elfie_id: str, request: TurnRequest):
        if (
            not request.message.strip()
            and not request.state_injection
            and not any(
                [
                    request.impact_force,
                    request.gentle_stroke,
                    request.salience_score >= 70,
                ]
            )
        ):
            raise HTTPException(status_code=422, detail="请输入消息或添加有效刺激")
        try:
            stimulus = StimulusBundle(
                message=request.message,
                temperature=request.temperature,
                is_network_online=request.is_network_online,
                salience_score=request.salience_score,
                impact_force=request.impact_force,
                impact_direction=request.impact_direction,
                gentle_stroke=request.gentle_stroke,
                state_injection=request.state_injection,
            )
            return sessions.get(elfie_id).run_turn(stimulus, request.mode)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/elfies/{elfie_id}/sessions/reset")
    def reset_session(elfie_id: str):
        try:
            return sessions.get(elfie_id).reset()
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return app
