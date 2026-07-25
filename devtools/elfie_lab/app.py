# 独立的本地 Web 服务，不依赖 ElfieNestEngine。

import base64
import binascii
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, AsyncIterator, Callable, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

import devtools.elfie_lab.api_models as api_models
import devtools.elfie_lab.runtime_foods as runtime_food_support
from ai_runtime.storage.data_home import get_elfie_developer_home, get_elfie_home
from devtools.elfie_lab.food_status import build_food_items, find_food_item
from devtools.elfie_lab.host import LoopbackHostMiddleware
from devtools.elfie_lab.media_store import (
    MAX_MEDIA_BYTES,
    ElfieLabMediaStore,
    InvalidMediaIdError,
    MediaNotFoundError,
    MediaStoreError,
)
from devtools.elfie_lab.profile_routes import build_profile_router
from devtools.elfie_lab.recycle_store import (
    RecycleMoveError,
    RecycleSourceNotFoundError,
    RecycleStore,
)
from devtools.elfie_lab.schemas import StimulusBundle
from devtools.elfie_lab.session import SessionClosedError
from devtools.elfie_lab.session_registry import SessionBusyError, SessionRegistry
from devtools.elfie_lab.static_host import mount_static_surfaces
from devtools.elfie_lab.storage import ElfieLabStorage
from devtools.runtime_lab import RuntimeLabConfigStore


def create_app(
    data_dir: Optional[str] = None,
    runtime_config_dir: Optional[str] = None,
    *,
    on_ready: Optional[Callable[[], None]] = None,
) -> FastAPI:
    storage = ElfieLabStorage(data_dir)
    runtime_root = runtime_config_dir or str(get_elfie_developer_home() / "runtime_lab")
    if Path(runtime_root).expanduser().resolve() == get_elfie_home().resolve():
        raise ValueError("Elfie Lab 不得使用生产 ELFIE_HOME 作为运行时配置目录")
    runtime_store = RuntimeLabConfigStore(runtime_root)
    food_store = runtime_food_support.runtime_food_catalog_store(runtime_store)
    configure_runtime_command = runtime_food_support.runtime_lab_command(runtime_store)
    developer_runtime = (
        Path(runtime_store.root).resolve()
        == (get_elfie_developer_home() / "runtime_lab").resolve()
    )
    sessions = SessionRegistry(storage, str(runtime_store.root))
    recycle_store = RecycleStore(storage.root)
    media_store = ElfieLabMediaStore(storage.root)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            if on_ready is not None:
                on_ready()
            yield
        finally:
            sessions.close()

    app = FastAPI(
        title="Elfie Lab",
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(LoopbackHostMiddleware)
    app.state.storage = storage
    app.state.sessions = sessions
    app.state.recycle_store = recycle_store
    app.state.media_store = media_store
    app.state.runtime_store = runtime_store
    app.state.food_store = food_store
    static_dir = mount_static_surfaces(app)
    app.include_router(build_profile_router(storage, sessions))

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(static_dir / "index.html")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "service": "elfie-lab"}

    @app.get("/api/runtime/status")
    def runtime_status():
        status = runtime_store.status()
        status["scope"] = "developer" if developer_runtime else "override"
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
    def create_elfie(request: api_models.CreateElfieRequest):
        try:
            spec = storage.create_elfie(
                request.name,
                request.species_id,
                request.age_years,
                request.description,
                appearance_description=request.appearance_description,
                personality_description=request.personality_description,
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

    @app.delete("/api/elfies/{elfie_id}")
    def delete_elfie(elfie_id: str):
        try:
            storage.get_elfie(elfie_id)
            sessions.remove(elfie_id, lambda: recycle_store.recycle(elfie_id))
        except SessionBusyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (KeyError, ValueError, RecycleSourceNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RecycleMoveError as exc:
            raise HTTPException(
                status_code=500,
                detail="精灵删除失败，原数据已回滚",
            ) from exc
        next_items = storage.list_elfies()
        return {
            "deleted_elfie_id": elfie_id,
            "next_elfie_id": next_items[0].elfie_id if next_items else None,
        }

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

    @app.post("/api/elfies/{elfie_id}/media", status_code=201)
    async def upload_media(elfie_id: str, file: Annotated[UploadFile, File()]):
        try:
            storage.get_elfie(elfie_id)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        content = await file.read(MAX_MEDIA_BYTES + 1)
        try:
            return media_store.store(elfie_id, content)._asdict()
        except MediaStoreError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.put("/api/elfies/{elfie_id}/portrait")
    def save_portrait(elfie_id: str, request: api_models.PortraitRequest):
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
    def create_turn(elfie_id: str, request: api_models.TurnRequest):
        food_key = request.food_key.lower().strip()
        try:
            food = find_food_item(
                food_key,
                runtime_store,
                food_store,
                configure_runtime_command,
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
            and request.vision_media_id is None
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
            vision_media = (
                media_store.descriptor_for(elfie_id, request.vision_media_id)._asdict()
                if request.vision_media_id is not None
                else None
            )
            stimulus = StimulusBundle(
                message=request.message,
                vision_media=vision_media,
                temperature=request.temperature,
                is_network_online=request.is_network_online,
                salience_score=request.salience_score,
                impact_force=request.impact_force,
                impact_direction=request.impact_direction,
                gentle_stroke=request.gentle_stroke,
                state_injection=request.state_injection,
            )
            return sessions.get(elfie_id).run_turn(stimulus, food_key)
        except InvalidMediaIdError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except MediaNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except SessionClosedError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/elfies/{elfie_id}/sessions/reset")
    def reset_session(elfie_id: str):
        try:
            return sessions.get(elfie_id).reset()
        except SessionClosedError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return app
