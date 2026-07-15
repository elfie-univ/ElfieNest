"""独立的本地 Web 服务，不依赖 ElfieNestEngine。"""

from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from devtools.elfie_lab.runtime_adapters import (
    list_installed_ollama_models,
    load_runtime_food_catalog,
    model_availability,
    runtime_food_catalog_store,
    runtime_lab_command,
)
from devtools.elfie_lab.schemas import StimulusBundle
from devtools.elfie_lab.session import SessionRegistry
from devtools.elfie_lab.storage import ElfieLabStorage
from devtools.runtime_lab import RuntimeLabConfigStore
from runtime.storage.data_home import get_elfie_home


class CreateElfieRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    anatomy_type: str = "biped"
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
    runtime_root = runtime_config_dir or str(get_elfie_home())
    runtime_store = RuntimeLabConfigStore(runtime_root)
    food_store = runtime_food_catalog_store(runtime_store)
    configure_runtime_command = runtime_lab_command(runtime_store)
    shared_runtime = Path(runtime_store.root).resolve() == get_elfie_home().resolve()
    sessions = SessionRegistry(storage, str(runtime_store.root))
    static_dir = Path(__file__).with_name("static")
    app.state.storage = storage
    app.state.sessions = sessions
    app.state.runtime_store = runtime_store
    app.state.food_store = food_store
    app.mount("/static", StaticFiles(directory=static_dir), name="elfie_lab_static")

    def food_items() -> list[Dict[str, Any]]:
        config = runtime_store.load_runtime_config()
        catalog = load_runtime_food_catalog(runtime_store, food_store)
        installed_models = list_installed_ollama_models(config)
        foods = []
        for key, recipe in catalog.recipes.items():
            primary = model_availability(
                recipe.primary.model,
                config,
                installed_models,
                configure_runtime_command,
            )
            fallback_states = [
                model_availability(
                    profile.model,
                    config,
                    installed_models,
                    configure_runtime_command,
                )
                for profile in recipe.technical_fallbacks
                if profile.model
            ]
            fallback_models = [
                profile.model for profile in recipe.technical_fallbacks if profile.model
            ]
            fallback_ready = any(item["ready"] for item in fallback_states)
            ready_for_attempt = bool(primary["ready"] or fallback_ready)
            setup_commands = []
            for item in [primary, *fallback_states]:
                command = str(item.get("command", ""))
                if command and command not in setup_commands:
                    setup_commands.append(command)
            foods.append(
                {
                    "key": key,
                    "display_name": recipe.display_name,
                    "description": recipe.description,
                    "model": recipe.primary.model,
                    "reasoning": recipe.primary.reasoning_profile.value,
                    "primary_ready": primary["ready"],
                    "fallback_ready": fallback_ready,
                    "fallback_models": fallback_models,
                    "ready_for_attempt": ready_for_attempt,
                    "credential_ready": ready_for_attempt,
                    "unavailable_reason": (
                        ""
                        if ready_for_attempt
                        else str(primary.get("reason", "粮食尚未就绪"))
                    ),
                    "setup_commands": setup_commands,
                }
            )
        mock_entry = {
            "key": "mock",
            "display_name": "模拟粮",
            "description": "离线可用，不调用任何外部服务",
            "model": "elfie-mock",
            "reasoning": "off",
            "primary_ready": True,
            "fallback_ready": False,
            "fallback_models": [],
            "ready_for_attempt": True,
            "credential_ready": True,
            "unavailable_reason": "",
            "setup_commands": [],
        }
        return [mock_entry, *foods]

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
        return {
            "items": food_items(),
            "configuration_command": configure_runtime_command,
        }

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
        food_key = request.food_key.lower().strip()
        food = (
            {"ready_for_attempt": True}
            if food_key == "mock"
            else {item["key"]: item for item in food_items()}.get(food_key)
        )
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
