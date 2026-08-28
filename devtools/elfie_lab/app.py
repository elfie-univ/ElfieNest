# 独立的本地 Web 服务，不依赖 ElfieNestEngine。

import base64
import binascii
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, AsyncIterator, Callable, Optional, Union

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

import devtools.elfie_lab.api_models as api_models
import devtools.elfie_lab.model_execution_foods as model_execution_food_support
from devtools.elfie_lab.evaluation_batches import BatchEvaluationService
from devtools.elfie_lab.evaluation_routes import build_evaluation_router
from devtools.elfie_lab.food_status import find_food_item
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
from devtools.elfie_lab.system_routes import build_system_router
from devtools.web_host import LabShell, frontend_shell
from infrastructure.persistence.configuration.species import (
    load_and_configure_species_catalog,
)
from infrastructure.persistence.layout.data_home import (
    get_elfie_developer_home,
    get_elfie_home,
)


def create_app(
    data_dir: Optional[str] = None,
    model_execution_config_dir: Optional[str] = None,
    *,
    on_ready: Optional[Callable[[], None]] = None,
    shell: LabShell = "elfie",
    default_path: str = "/elfie/experiment",
    nest_data_dir: Optional[Union[str, Path]] = None,
    nest_http_port: int = 9001,
    nest_godot_ws_port: Optional[int] = None,
) -> FastAPI:
    """Create the Elfie Lab HTTP app.

    ``shell="elfie"`` keeps the standalone application contract intact.  The
    unified Developer Tools entry point passes ``shell="unified"`` and a
    Nest data directory so all three browser surfaces share this one HTTP
    listener while retaining separate data ownership and the existing internal
    Godot WebSocket gateway.
    """
    load_and_configure_species_catalog()
    storage = ElfieLabStorage(data_dir)
    config_root = model_execution_config_dir or str(storage.root / "runtime")
    if Path(config_root).expanduser().resolve() == get_elfie_home().resolve():
        raise ValueError("Elfie Lab 不得使用生产 ELFIE_HOME 作为模型执行配置目录")
    model_environment = model_execution_food_support.ElfieLabModelEnvironment(
        config_root
    )
    food_store = model_execution_food_support.model_execution_food_catalog_store(
        model_environment
    )
    developer_scope = (
        model_environment.root.resolve()
        == (get_elfie_developer_home() / "elfie_lab" / "runtime").resolve()
    )
    sessions = SessionRegistry(storage, str(model_environment.root))
    recycle_store = RecycleStore(storage.root)
    media_store = ElfieLabMediaStore(storage.root)
    evaluation_service = BatchEvaluationService(
        storage.root / "evaluations",
        str(model_environment.root),
    )
    nest_world = None
    nest_runtime_startup_error: Optional[str] = None
    if shell == "unified":
        from devtools.nest_lab.world import NestLabWorld

        nest_root = (
            Path(nest_data_dir).expanduser().resolve()
            if nest_data_dir is not None
            else get_elfie_developer_home() / "nest_lab"
        )
        nest_root.mkdir(parents=True, exist_ok=True)
        nest_world = NestLabWorld(
            data_dir=nest_root,
            http_port=nest_http_port,
            websocket_port=nest_godot_ws_port or nest_http_port + 1,
        )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        nonlocal nest_runtime_startup_error
        try:
            if nest_world is not None:
                try:
                    nest_world.start()
                except RuntimeError as error:
                    # Keep the unified HTTP shell usable when the optional
                    # Godot gateway port is occupied.  The Nest page exposes
                    # the degraded state through its existing runtime API.
                    nest_runtime_startup_error = str(error)
            if on_ready is not None:
                on_ready()
            yield
        finally:
            if nest_world is not None:
                nest_world.stop()
            evaluation_service.close()
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
    app.state.model_execution = model_environment
    app.state.food_store = food_store
    app.state.evaluation_service = evaluation_service
    app.state.nest_world = nest_world
    mount_static_surfaces(app)
    godot_web_entry = (
        Path(__file__).parents[2]
        / "build"
        / "components"
        / "godot-web"
        / "elfienest.html"
    )
    unified_godot_web_ready = (
        godot_web_entry.is_file() if nest_world is not None else False
    )
    app.state.godot_web_ready = unified_godot_web_ready
    app.include_router(build_profile_router(storage, sessions))
    app.include_router(
        build_system_router(
            model_environment,
            food_store,
            developer_scope=developer_scope,
        )
    )
    app.include_router(
        build_evaluation_router(
            storage=storage,
            sessions=sessions,
            service=evaluation_service,
            model_environment=model_environment,
            food_store=food_store,
        )
    )
    if nest_world is not None:
        from devtools.nest_lab.routes import build_router as build_nest_router

        app.include_router(build_nest_router(nest_world))

        @app.get("/api/godot-web")
        def godot_web_status() -> dict[str, object]:
            return {
                "ready": unified_godot_web_ready,
                "entry_url": "/godot-web/elfienest.html"
                if unified_godot_web_ready
                else "",
                "build_command": "./developer.sh build-godot-web",
            }

    @app.get("/", include_in_schema=False)
    def index() -> RedirectResponse:
        return RedirectResponse(default_path, status_code=307)

    @app.get("/elfie/experiment", include_in_schema=False)
    def experiment_page() -> HTMLResponse:
        return frontend_shell(shell)

    @app.get("/elfie/evaluations", include_in_schema=False)
    def evaluations_page() -> HTMLResponse:
        return frontend_shell(shell)

    if nest_world is not None:

        @app.get("/nest/experiment", include_in_schema=False)
        def nest_experiment_page() -> HTMLResponse:
            return frontend_shell(shell)

    @app.get("/api/health")
    def health():
        payload: dict[str, object] = {
            "status": "degraded" if nest_runtime_startup_error is not None else "ok",
            "service": "developer-tools" if nest_world is not None else "elfie-lab",
        }
        if nest_world is not None:
            payload["scope"] = "developer"
            payload["production_engine"] = False
            payload["runtime_startup_error"] = nest_runtime_startup_error or ""
        return payload

    @app.get("/api/elfies")
    def list_elfies():
        items = []
        for item in storage.list_elfies():
            payload = item.to_dict()
            if storage.portrait_path(item.elfie_id).is_file():
                payload["portrait_url"] = f"/api/elfies/{item.elfie_id}/portrait"
            items.append(payload)
        return {"items": items}

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
            if evaluation_service.has_active_run(elfie_id):
                raise HTTPException(
                    status_code=409,
                    detail="该测试精灵的评测仍在运行，请等待完成后再删除",
                )
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
                model_environment,
                food_store,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if food is None:
            raise HTTPException(
                status_code=422,
                detail=f"Runtime 粮食目录中不存在粮食: {food_key}",
            )
        if not food["ready_for_attempt"]:
            raise HTTPException(
                status_code=422,
                detail=f"粮食“{food['display_name']}”尚未配置：{food['unavailable_reason']}",
            )
        if (
            not request.message.strip()
            and request.vision_media_id is None
            and not request.attachments
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
            message_attachments = [
                {
                    **media_store.descriptor_for(
                        elfie_id, attachment.media_id
                    )._asdict(),
                    "filename": attachment.filename,
                }
                for attachment in request.attachments
            ]
            stimulus = StimulusBundle(
                source_domain=request.source_domain,
                message=request.message,
                vision_media=vision_media,
                message_attachments=message_attachments,
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


def create_unified_app(
    data_dir: Optional[Union[str, Path]] = None,
    *,
    http_port: int = 9001,
    godot_ws_port: Optional[int] = None,
    on_ready: Optional[Callable[[], None]] = None,
    default_path: str = "/elfie/experiment",
) -> FastAPI:
    """Create the single-port Developer Tools surface.

    The parent directory owns the two isolated stores.  This keeps Elfie
    session/evaluation data and Nest/Godot experiment data independent while
    presenting one browser origin and one user-facing HTTP port.
    """
    root = (
        Path(data_dir).expanduser().resolve()
        if data_dir is not None
        else get_elfie_developer_home()
    )
    return create_app(
        str(root / "elfie_lab"),
        shell="unified",
        default_path=default_path,
        nest_data_dir=root / "nest_lab",
        nest_http_port=http_port,
        nest_godot_ws_port=godot_ws_port,
        on_ready=on_ready,
    )
