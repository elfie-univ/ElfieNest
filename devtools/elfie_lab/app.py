"""独立的本地 Web 服务，不依赖 ElfieNestEngine。"""

import base64
import binascii
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from ai_runtime.storage.data_home import get_elfie_home
from devtools.elfie_lab.food_status import build_food_items, mock_food_item
from devtools.elfie_lab.runtime_adapters import (
    runtime_food_catalog_store,
    runtime_lab_command,
)
from devtools.elfie_lab.schemas import StimulusBundle
from devtools.elfie_lab.session_registry import SessionRegistry
from devtools.elfie_lab.storage import ElfieLabStorage
from devtools.runtime_lab import RuntimeLabConfigStore


class CreateElfieRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    species_id: str = "fox"
    description: str = Field(default="", max_length=240)


class TurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(default="", max_length=8000)
    food_key: str = Field(min_length=1, max_length=40)
    temperature: float = Field(default=24.0, ge=-50.0, le=100.0)
    is_network_online: bool = True
    salience_score: float = Field(default=20.0, ge=0.0, le=100.0)
    impact_force: float = Field(default=0.0, ge=0.0, le=1000.0)
    impact_direction: str = Field(default="none", max_length=40)
    gentle_stroke: float = Field(default=0.0, ge=0.0, le=100.0)
    state_injection: Dict[str, Any] = Field(default_factory=dict)


class PortraitRequest(BaseModel):
    data_url: str = Field(min_length=32, max_length=7_000_000)


def create_app(
    data_dir: Optional[str] = None, runtime_config_dir: Optional[str] = None
) -> FastAPI:
    storage = ElfieLabStorage(data_dir)
    runtime_root = runtime_config_dir or str(get_elfie_home())
    runtime_store = RuntimeLabConfigStore(runtime_root)
    food_store = runtime_food_catalog_store(runtime_store)
    configure_runtime_command = runtime_lab_command(runtime_store)
    shared_runtime = Path(runtime_store.root).resolve() == get_elfie_home().resolve()
    sessions = SessionRegistry(storage, str(runtime_store.root))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            sessions.close()

    app = FastAPI(
        title="Elfie Lab",
        description="单精灵开发者调试平台",
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    static_dir = Path(__file__).with_name("static")
    app.state.storage = storage
    app.state.sessions = sessions
    app.state.runtime_store = runtime_store
    app.state.food_store = food_store
    app.mount("/static", StaticFiles(directory=static_dir), name="elfie_lab_static")
    godot_web_dir = Path(__file__).parents[2] / "build" / "components" / "godot-web"
    if godot_web_dir.is_dir():
        app.mount(
            "/godot-web",
            StaticFiles(directory=godot_web_dir, html=True),
            name="elfie_lab_godot_web",
        )

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(static_dir / "index.html")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "service": "elfie-lab"}

    @app.get("/api/runtime/status")
    def runtime_status():
        status = runtime_store.status()
        status["scope"] = "shared" if shared_runtime else "override"
        return status

    @app.get("/api/runtime/foods")
    def runtime_foods():
        """读取本机公共 Runtime 配置的粮食目录。"""
        try:
            items = build_food_items(
                runtime_store,
                food_store,
                configure_runtime_command,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {
            "items": items,
            "configuration_command": configure_runtime_command,
        }

    @app.get("/api/elfies")
    def list_elfies():
        return {"items": [item.to_dict() for item in storage.list_elfies()]}

    @app.post("/api/elfies", status_code=201)
    def create_elfie(request: CreateElfieRequest):
        try:
            spec = storage.create_elfie(
                request.name, request.species_id, request.description
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

    @app.get("/api/elfies/{elfie_id}/portrait", include_in_schema=False)
    def get_portrait(elfie_id: str):
        try:
            storage.get_elfie(elfie_id)
            path = storage.portrait_path(elfie_id)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if not path.is_file():
            raise HTTPException(status_code=404, detail="该精灵尚未保存头像")
        return FileResponse(path, media_type="image/png")

    @app.put("/api/elfies/{elfie_id}/portrait")
    def save_portrait(elfie_id: str, request: PortraitRequest):
        try:
            storage.get_elfie(elfie_id)
            prefix = "data:image/png;base64,"
            if not request.data_url.startswith(prefix):
                raise HTTPException(
                    status_code=422,
                    detail="头像数据必须是 PNG data URL",
                )
            content = base64.b64decode(request.data_url[len(prefix) :], validate=True)
            storage.save_portrait(elfie_id, content)
        except (KeyError, ValueError, binascii.Error) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"portrait_url": f"/api/elfies/{elfie_id}/portrait"}

    @app.post("/api/elfies/{elfie_id}/turns")
    def create_turn(elfie_id: str, request: TurnRequest):
        food_key = request.food_key.lower().strip()
        try:
            food = (
                mock_food_item()
                if food_key == "mock"
                else {
                    item["key"]: item
                    for item in build_food_items(
                        runtime_store,
                        food_store,
                        configure_runtime_command,
                    )
                }.get(food_key)
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if food is None:
            raise HTTPException(
                status_code=422,
                detail=f"Runtime 粮食目录中不存在粮食: {food_key}",
            )
        if not food["ready_for_attempt"]:
            command = next(iter(food["setup_commands"]), "")
            command_hint = f"；请运行：{command}" if command else ""
            raise HTTPException(
                status_code=422,
                detail=f"粮食“{food['display_name']}”尚未就绪：{food['unavailable_reason']}{command_hint}",
            )
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
            return sessions.get(elfie_id).run_turn(stimulus, food_key)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/elfies/{elfie_id}/sessions/reset")
    def reset_session(elfie_id: str):
        try:
            return sessions.get(elfie_id).reset()
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return app
