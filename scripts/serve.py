#!/usr/bin/env python3
"""ElfieNest backend service — FastAPI + engine background thread + DB-driven dynamic Elfie loading.

Startup flow:
    1. Initialize DB + seed Owner account
    2. Optional: seed initial Elfie "Aifei" for Owner (--seed-elfie, default on)
    3. Engine background thread: RuntimeAgent → ElfieNestEngine (no hardcoded Elfies)
    4. Load final Elfie records → instantiate Elfie → register to engine
    5. Create FastAPI app → uvicorn blocks main thread

Command-line arguments:
    --fallback      Use built-in dialogue engine (no Ollama connection)
    --port          HTTP port (default 8000)
    --ws-port       Auth WebSocket port (default 8766)
    --no-seed-elfie Do not auto-seed initial Elfie
    --force         Force restart (kill processes occupying ports)

CLI tools:
    .venv/bin/python scripts/elfienest.py config    Open config TUI
    .venv/bin/python scripts/elfienest.py owner     Manage Owner account
    .venv/bin/python scripts/elfienest.py doctor    Run local diagnostics
    .venv/bin/python scripts/elfienest.py status    View service status
    .venv/bin/python scripts/elfienest.py setup     First-time setup wizard
    .venv/bin/python scripts/elfienest.py restart   Restart service
    .venv/bin/python scripts/elfienest.py stop      Stop service
"""

import argparse
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional, Protocol, Sequence
from uuid import uuid4

from pydantic import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.WARNING, format="%(message)s")

from ai_runtime import LLMRuntimeConfig
from ai_runtime.gateway.request import (
    StructuredRuntimeCapabilities,
    StructuredRuntimeRequest,
    StructuredRuntimeResult,
)
from app.bootstrap import create_app
from app.bootstrap.food import build_food_service
from app.bootstrap.lifecycle import create_lifecycle_facade
from app.bootstrap.nest_session import build_nest_session_services
from app.features.adoption import (
    AcceptedAdoptionReservation,
    AdoptionReservationRecord,
)
from app.interfaces.api.service_access import ServiceMode
from app.interfaces.cli.lifecycle_commands import _remember_lifecycle_data_home
from app.interfaces.web.frontend_build import (
    FrontendBuildError,
    ensure_frontend_build,
)
from app.orchestration.lifecycle import (
    DEFAULT_GODOT_WS_PORT,
    DEFAULT_MANAGEMENT_WS_PORT,
    MANAGED_START_ENV,
    RecoveryInProgressError,
    command_runs_service,
    validate_service_ports,
)
from elfie.brain.decision_types import CancelPolicy, DecisionPlan, MessageIntent
from elfie.brain.model_context_compiler import CompiledModelContext
from elfie.message_types import EventId, IntentId, PlanId, TurnId
from infrastructure.godot.gateway.bundle import inspect_godot_web_bundle
from infrastructure.persistence.account_repository import AccountRepository
from infrastructure.persistence.adoption import SQLiteAdoptionAdapter
from infrastructure.persistence.adoption_profiles import FinalElfieWorkspaceAdapter
from infrastructure.persistence.data_home import (
    DataHomeSelectionError,
    data_home_from_db_path,
    get_db_path,
    get_elfie_config_dir,
    get_elfie_home,
    select_elfie_home,
)
from infrastructure.persistence.elfies import SQLiteElfiesProjectionAdapter
from infrastructure.persistence.food_catalog import SQLiteFoodPackageRepository
from infrastructure.persistence.store import (
    get_db,
    init_db,
    seed_initial_owner_if_env_set,
)


class FallbackAgent:
    """Lightweight mock dialogue engine when Ollama is unavailable."""

    class MockConfig:
        remote_api_key = ""
        providers = {
            "deepseek": {"api_key": "", "api_base": ""},
            "openai": {"api_key": "", "api_base": ""},
            "gemini": {"api_key": "", "api_base": ""},
            "qwen": {"api_key": "", "api_base": ""},
            "ollama": {"api_key": "", "api_base": "http://localhost:11434"},
        }

    config = MockConfig()

    def ask(self, prompt, energy=100, task_complexity=1, allowed_skills=None):
        import random  # noqa: PLC0415

        prompt_lower = prompt.lower()
        if any(kw in prompt_lower for kw in ["hello", "hi", "hey"]):
            return (
                "Hello! I am Aifei, a cheerful little Elfie. "
                "What would you like to talk about today? [ACTION]nod_head[/ACTION]"
            )
        if any(kw in prompt_lower for kw in ["name", "who are you"]):
            return (
                "My name is Aifei! I am an Elfie living inside ElfieNest. "
                "I am still small, curious, and learning how to be helpful."
                " [ACTION]nod_head[/ACTION]"
            )
        if any(kw in prompt_lower for kw in ["weather", "today"]):
            return (
                "It feels calm in here today. "
                "I do not have a real window, but I can imagine warm light nearby. "
                "[ACTION]stretch[/ACTION]"
            )
        if any(kw in prompt_lower for kw in ["happy", "joy", "glad"]):
            return "I am happy you came to chat with me.  [ACTION]waggle_ears[/ACTION]"
        if any(kw in prompt_lower for kw in ["eat", "hungry", "food", "snack"]):
            return (
                "Snacks sound lovely. I may not need food the way people do, "
                "but I still like imagining something tasty. [ACTION]lick_lips[/ACTION]"
            )
        if any(kw in prompt_lower for kw in ["sleep", "tired", "good night"]):
            return "I am getting a little sleepy, but I can stay with you a bit longer. [ACTION]yawn[/ACTION]"
        if any(kw in prompt_lower for kw in ["bye", "goodbye", "quit", "exit"]):
            return "Goodbye! Come back whenever you want to talk. [ACTION]wave[/ACTION]"

        replies = [
            "I am listening. Please keep going. [ACTION]nod_head[/ACTION]",
            "I think I understand a little better now. [ACTION]nod_head[/ACTION]",
            "That is interesting. Tell me more. [ACTION]tilt_head[/ACTION]",
            "I do not fully understand yet, but I will keep trying. [ACTION]nod_head[/ACTION]",
            "I am here with you, and I like hearing what you think. [ACTION]nod_head[/ACTION]",
        ]
        return random.choice(replies)

    def structured_capabilities(
        self,
        food_key=None,
        food_unavailable=False,
    ) -> StructuredRuntimeCapabilities:
        """Expose the deterministic fallback through Brain's Runtime contract."""
        return StructuredRuntimeCapabilities(
            provider="fallback",
            model_key="fallback/local",
            supports_json_schema=False,
            supports_tool_calling=False,
            supports_json_mode=True,
            supports_plain_text=True,
            max_output_tokens=512,
        )

    def generate_structured(
        self,
        request: StructuredRuntimeRequest,
    ) -> StructuredRuntimeResult:
        """Return a structured chat plan for trusted Owner events."""
        owner_context = self._owner_chat_context(request.prompt)
        if owner_context is None:
            text = self.ask(request.prompt, allowed_skills=[])
        else:
            channel_id, conversation_id, content = owner_context
            text = self._owner_message_plan(
                channel_id=channel_id,
                conversation_id=conversation_id,
                content=self.ask(content, allowed_skills=[]),
            )
        return request.to_result(
            text=text,
        )

    @staticmethod
    def _owner_chat_context(prompt: str) -> Optional[tuple[str, str, str]]:
        """Extract only host-compiled Owner chat routing fields."""
        try:
            context = CompiledModelContext.model_validate_json(prompt)
        except ValidationError:
            return None
        for event in context.events:
            if event.modality != "social:message":
                continue
            if event.actor.source_kind != "owner" or event.channel_id is None:
                continue
            return (
                event.channel_id,
                f"owner:{event.actor.actor_id}",
                event.content,
            )
        return None

    @staticmethod
    def _owner_message_plan(
        *,
        channel_id: str,
        conversation_id: str,
        content: str,
    ) -> str:
        """Build one valid MessageIntent plan for the existing chat bridge."""
        now = datetime.now(timezone.utc)
        deadline = now + timedelta(seconds=45)
        cause_event_id = EventId(f"fallback-cause-{uuid4().hex}")
        intent = MessageIntent(
            type="message",
            intent_id=IntentId(f"fallback-message-{uuid4().hex}"),
            cause_event_ids=(cause_event_id,),
            dependency_ids=(),
            deadline=deadline,
            cancel_policy=CancelPolicy.IF_NOT_STARTED,
            channel_id=channel_id,
            conversation_id=conversation_id,
            content=content,
        )
        plan = DecisionPlan(
            plan_id=PlanId(f"fallback-plan-{uuid4().hex}"),
            turn_id=TurnId(f"fallback-turn-{uuid4().hex}"),
            frame_id=EventId(f"fallback-frame-{uuid4().hex}"),
            context_revision=0,
            capability_revision=0,
            created_at=now,
            deadline=deadline,
            cause_event_ids=(cause_event_id,),
            intents=(intent,),
        )
        return plan.model_dump_json()


def remaining_occupied_ports(
    occupied: Sequence[tuple[int, str]],
    is_port_in_use_func: Callable[[int], bool],
) -> list[tuple[int, str]]:
    """Return ports that remain occupied after force cleanup."""
    return [(port, name) for port, name in occupied if is_port_in_use_func(port)]


def service_host(lan: bool) -> str:
    """Keep developer CLI loopback-only unless the caller explicitly enables LAN."""
    return "0.0.0.0" if lan else "127.0.0.1"


class GodotBuildCommandResult(Protocol):
    """Minimal Godot build command result contract for tests without Godot."""

    returncode: int


GodotBuildCommandRunner = Callable[[list[str]], GodotBuildCommandResult]


def prepare_godot_web_runtime(
    runtime_mode: str,
    run_command: GodotBuildCommandRunner = subprocess.run,
    is_frozen: bool = bool(getattr(sys, "frozen", False)),
) -> bool:
    """Ensure or validate Godot Web Runtime for the selected mode, returning availability."""
    if runtime_mode == "release" and is_frozen:
        return True
    action = "--ensure" if runtime_mode == "development" else "--check"
    command = [
        sys.executable,
        str(Path(__file__).with_name("build_godot_web.py")),
        action,
    ]
    return run_command(command).returncode == 0


def prepare_frontend_web_runtime(runtime_mode: str) -> None:
    """Ensure the source Web client is current before a development launch."""
    if runtime_mode == "development":
        ensure_frontend_build(runtime_mode=runtime_mode)


def seed_single_elfie(db_path: str) -> bool:
    """Seed one final default Elfie named "Aifei" for an otherwise empty Nest.

    Returns:
        True when a new Elfie was seeded, False when existing Elfies require no action.
    """
    elfies = SQLiteElfiesProjectionAdapter(db_path)
    if elfies.list_directory():
        return False
    with get_db(db_path) as connection:
        owner = AccountRepository(connection).find_owner()
    if owner is None:
        return False

    elfie_id = "00000001"
    birth_date = datetime.now(timezone.utc).date().isoformat()
    adoption = SQLiteAdoptionAdapter(db_path)
    adoption.reserve(
        AdoptionReservationRecord(
            elfie_id=elfie_id,
            owner_user_id=owner.user_id,
            name="Aifei",
            species_id="fox",
            gender="female",
            birth_date=birth_date,
            summary="好奇探索",
        ),
        default_limit=1,
    )
    try:
        FinalElfieWorkspaceAdapter(data_home_from_db_path(db_path)).materialize(
            AcceptedAdoptionReservation(
                elfie_id=elfie_id,
                owner_user_id=owner.user_id,
                name="Aifei",
                species_id="fox",
                personality_style="好奇探索",
                height="tall",
                build="plump",
                appearance_seed=uuid4().int & ((1 << 63) - 1),
                face="any",
                signature="any",
                gender="female",
                birth_date=birth_date,
            )
        )
    except Exception:
        adoption.release(elfie_id)
        raise

    return True


def main():
    lifecycle = create_lifecycle_facade()
    parser = argparse.ArgumentParser(description="ElfieNest backend service")
    parser.add_argument(
        "--fallback",
        action="store_true",
        help="Use built-in dialogue engine (no Ollama connection)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="HTTP port (default 8000)",
    )
    parser.add_argument(
        "--ws-port",
        type=int,
        default=DEFAULT_MANAGEMENT_WS_PORT,
        help="Auth WebSocket port (default 8766)",
    )
    parser.add_argument(
        "--godot-ws-port",
        type=int,
        default=DEFAULT_GODOT_WS_PORT,
        help="Godot WebSocket port (default 8765)",
    )
    parser.add_argument(
        "--no-seed-elfie",
        action="store_true",
        help="Do not auto-seed initial Elfie",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force restart: kill processes occupying ports",
    )
    parser.add_argument(
        "--lan",
        action="store_true",
        help="Listen on LAN IPv4 address explicitly (default: localhost only)",
    )
    parser.add_argument(
        "--runtime-mode",
        choices=("development", "release"),
        default=os.environ.get("ELFIENEST_RUNTIME_MODE", "development"),
        help="Godot Web Runtime lifecycle mode (default: development)",
    )
    parser.add_argument(
        "--data-home",
        default=None,
        help="Use an explicit ElfieNest data root for this serve process",
    )
    args = parser.parse_args()

    try:
        select_elfie_home(
            args.data_home,
            invoking_cwd=Path.cwd(),
            runtime_mode=args.runtime_mode,
            source_root=Path(__file__).resolve().parent.parent,
        )
    except DataHomeSelectionError as error:
        parser.error(str(error))

    port_error = validate_service_ports(
        args.port,
        args.ws_port,
        args.godot_ws_port,
    )
    if port_error:
        parser.error(port_error)

    try:
        prepare_frontend_web_runtime(args.runtime_mode)
    except FrontendBuildError as error:
        print(f"  ❌ Frontend Web build failed: {error}")
        raise SystemExit(1) from None

    managed_start = os.environ.pop(MANAGED_START_ENV, "") == "1"
    try:
        start_lease = lifecycle.acquire_start_lease(
            get_elfie_home(), blocking=managed_start
        )
    except (OSError, RecoveryInProgressError):
        print(
            "  ❌ Owner account recovery or another service start in progress, cannot start"
        )
        raise SystemExit(1) from None

    godot_ready = prepare_godot_web_runtime(args.runtime_mode)
    if not godot_ready and args.runtime_mode == "release":
        print(
            "  ❌ Release mode requires verified Godot Web Runtime, service not started"
        )
        raise SystemExit(1)
    if not godot_ready:
        print(
            "  ⚠️  Godot Web Runtime auto-build failed, service still available for chat; please fix 3D preview via diagnostics"
        )

    godot_web = inspect_godot_web_bundle()
    if godot_web.ready:
        print(f"  ✅ Godot Web Runtime: {godot_web.entry_url}")
    else:
        print("  ⚠️  Godot Web Runtime not built yet; 3D room unavailable")
        print(
            "  💡 Run after modifying Godot assets or before release: ./elfienest.sh build-godot-web"
        )

    def is_port_in_use(port):
        return lifecycle.ports_in_use((port,))

    def kill_process_on_port(port):
        """Terminate only the current project's registered service process."""
        expected_root = Path(__file__).resolve().parent.parent
        expected_script = Path(__file__).resolve()
        try:
            occupant = lifecycle.port_occupant_pid(port)
            pids = (occupant,) if occupant is not None else ()
            killed = []
            for pid in pids:
                try:
                    snapshot = lifecycle.inspect_process(pid)
                    process_cwd = snapshot.cwd.resolve()
                except (OSError, ValueError, RuntimeError):
                    continue
                if process_cwd != expected_root or not command_runs_service(
                    snapshot.command, process_cwd, expected_script
                ):
                    continue
                try:
                    lifecycle.terminate_process(pid, force=True)
                    killed.append(str(pid))
                except OSError:
                    pass
            return killed
        except OSError:
            return []

    ports_to_check = [
        (args.port, "HTTP"),
        (args.ws_port, "WebSocket"),
        (args.godot_ws_port, "Godot WebSocket"),
    ]

    occupied = []
    for port, name in ports_to_check:
        if is_port_in_use(port):
            occupied.append((port, name))

    if occupied:
        if args.force:
            print("\n" + "=" * 56)
            print("  🔄 Force restart mode: terminating processes on occupied ports...")
            print("=" * 56)
            for port, name in occupied:
                pids = kill_process_on_port(port)
                if pids:
                    print(
                        f"  ✓ Port {port} ({name}): terminated process PID {', '.join(pids)}"
                    )
                else:
                    print(f"  ⚠ Port {port} ({name}): unable to terminate")
            print()
            time.sleep(1)
            remaining = remaining_occupied_ports(occupied, is_port_in_use)
            if remaining:
                print("=" * 56)
                print("  ❌ Force restart failed, ports still occupied")
                print("=" * 56)
                for port, name in remaining:
                    print(f"  ❌ Port {port} ({name}) still occupied")
                print("  Please manually close these processes and retry.")
                print("=" * 56 + "\n")
                start_lease.release()
                sys.exit(1)
        else:
            print("\n" + "=" * 56)
            print("  ⚠️  Port conflict, cannot start service")
            print("=" * 56)
            for port, name in occupied:
                print(f"  ❌ Port {port} ({name}) already in use")
            print("\n  💡 Solutions:")
            print("     1. Force restart (auto-kill occupying processes):")
            print("        ./elfienest.sh --force")
            print("        or")
            print("        elfienest --force")
            print("     2. Manually close and retry")
            print("     3. Use different ports:")
            print("        ./elfienest.sh --port 8001 --ws-port 8866")
            print("=" * 56 + "\n")
            start_lease.release()
            sys.exit(1)

    try:
        lifecycle.register_current_service(get_elfie_home())
        _remember_lifecycle_data_home(get_elfie_home())
    except OSError as error:
        start_lease.release()
        print(f"  ❌ Cannot register service process: {error}")
        raise SystemExit(1) from None
    start_lease.release()
    db_path = str(get_db_path())

    # 1. Initialize the final database and seed Owner from environment.
    init_db(db_path)
    seed_initial_owner_if_env_set(db_path)
    food_repository = SQLiteFoodPackageRepository(db_path)
    food_service = build_food_service(db_path)

    # 2. Optionally seed the initial Owner Elfie (enabled by default).
    if not args.no_seed_elfie:
        if seed_single_elfie(db_path):
            print('  🌱 Auto-seeded Elfie "Aifei" for Owner (--seed-elfie)')

    # 3. Start the engine worker thread.
    engine_holder: dict = {}
    engine_ready = threading.Event()

    def engine_worker():
        config = LLMRuntimeConfig(
            ollama_host="http://localhost:11434",
        )

        # Read engine configuration.
        engine_config = config.system.get("engine", {})
        tick_interval_sec = engine_config.get("tick_interval_sec", 1.5)

        runtime_agent: Optional[Any] = None
        main_food_loader: Optional[Callable[[str], Any]] = None
        if args.fallback:
            runtime_agent = FallbackAgent()
            print("  ⚡ Using built-in dialogue engine (--fallback mode)")
        else:
            try:
                from ai_runtime import RuntimeAgent  # noqa: PLC0415
                from app.bootstrap.runtime_food import (  # noqa: PLC0415
                    final_main_food_loader,
                )

                main_food_loader = final_main_food_loader(food_service)
                raw_agent = RuntimeAgent(
                    config,
                    live_reload=True,
                    main_food_loader=main_food_loader,
                    food_catalog_repository=food_repository,
                )
                runtime_agent = raw_agent
                print(
                    "  ✅ Runtime connected, will select local or cloud models via food policy"
                )
                print("  ⏳ Warming up model (first load takes 10-15 seconds)...")

                def _warmup():
                    try:
                        raw_agent.ask(
                            "hello",
                            energy=100,
                            task_complexity=1,
                            allowed_skills=[],
                        )
                        print("  ✅ Model warm-up complete, ready to chat!")
                    except Exception as e:
                        print(f"  ⚠️  Model warm-up error: {e}")

                threading.Thread(target=_warmup, daemon=True).start()
            except Exception as error:  # noqa: BLE001
                print(f"  ⚠️  Runtime initialization failed: {error}")

        if runtime_agent is None:
            runtime_agent = FallbackAgent()
            print(
                "  ⚡ Ollama auto-start failed or not installed, using built-in dialogue engine"
            )
            print(
                "  💡 For real AI responses, ensure Ollama is installed locally:\n"
                "     Setup guide: .venv/bin/python ai_runtime/setup/runtime_setup.py"
            )

        nest_session = build_nest_session_services(
            db_path,
            runtime=runtime_agent,
            godot_ws_port=args.godot_ws_port,
            http_port=args.port,
            tick_interval_sec=tick_interval_sec,
            main_food_loader=main_food_loader,
        )
        lifecycle.start_runtime_channel(nest_session.world_runtime)
        engine = nest_session.engine
        engine_holder["engine"] = engine
        engine_holder["world_runtime"] = nest_session.world_runtime
        engine_ready.set()
        engine.start_loop(
            runtime_factory=nest_session.runtime_factory,
            ticks_to_run=100000,
        )

    engine_thread = threading.Thread(target=engine_worker, daemon=True)
    engine_thread.start()

    engine_ready.wait(timeout=5.0)
    if "engine" not in engine_holder:
        print("❌ Engine failed to become ready within 5s")
        sys.exit(1)
    engine = engine_holder["engine"]
    time.sleep(2.0)  # Wait for service readiness.
    print("  ℹ️ Godot Web Runtime is hosted by ElfieNest Desktop hidden window")

    # 4. Dynamically load all Elfies from the database.
    loaded_elfies: list[dict] = []
    try:
        from elfie import ElfieFactory  # noqa: PLC0415

        elfie_factory = ElfieFactory()

        rows = SQLiteElfiesProjectionAdapter(db_path).list_directory()
        for row in rows:
            elfie_id = row.elfie_id
            config_dir = str(get_elfie_config_dir(elfie_id))
            name = row.name
            try:
                elfie = elfie_factory.restore(
                    config_dir,
                    godot_api=engine.world_runtime,
                    elfie_id=elfie_id,
                )
                engine.session.register_elfie(elfie_id, elfie)
                loaded_elfies.append({"id": elfie_id, "name": name})
            except Exception as e:
                print(f"  ⚠️  Failed to load Elfie {name} ({elfie_id}) failed: {e}")
    except Exception as e:
        print(f"  ⚠️  Failed to query Elfie list: {e}")

    # 5. Print startup information.
    print()
    print("=" * 56)
    print("  🦊 ElfieNest Embodied AI Creature Service")
    print("=" * 56)
    print(f"  🌐 HTTP:    http://127.0.0.1:{args.port}")
    print(f"  🔌 WebSocket (admin): ws://127.0.0.1:{args.ws_port}")
    print(f"  🔌 WebSocket(Godot): ws://127.0.0.1:{args.godot_ws_port}")
    if loaded_elfies:
        names_str = ", ".join(e["name"] for e in loaded_elfies)
        print(f"  ✨ Loaded {len(loaded_elfies)}  Elfie(s): {names_str}")
    else:
        print("  ✨ No Elfie loaded (adopt one after login)")
    print()
    print(f"  📖 Open in browser: http://127.0.0.1:{args.port}/")
    print("  ⌨️  Press Ctrl+C to stop")
    print("=" * 56)
    print()

    # 6. Create the FastAPI app and start uvicorn on the main thread.
    app = create_app(
        engine=engine,
        db_path=db_path,
        ws_port=args.ws_port,
        http_port=args.port,
        service_mode=ServiceMode.LAN.value if args.lan else ServiceMode.LOOPBACK.value,
    )

    import uvicorn  # noqa: PLC0415

    try:
        uvicorn.run(
            app,
            host=service_host(args.lan),
            limit_concurrency=100,
            port=args.port,
            log_level="warning",
        )
    except KeyboardInterrupt:
        print("\nShutting down service...")
    finally:
        lifecycle.stop_runtime_channel(engine_holder["world_runtime"])
        print("Service stopped.")


if __name__ == "__main__":
    main()
