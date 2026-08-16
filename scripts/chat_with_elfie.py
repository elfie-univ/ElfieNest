#!/usr/bin/env python3
"""ElfieNest interactive chat client.

Starts the full service stack so the user can chat with a persisted Elfie in the terminal.
"""

import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)-25s - %(levelname)-6s - %(message)s",
)
logger = logging.getLogger("chat")

from app.bootstrap.app_wiring.storage import ensure_application_storage
from app.bootstrap.model_execution import build_model_execution_services
from app.bootstrap.system_wiring.entrypoints import get_db_path
from app.bootstrap.system_wiring.lifecycle import create_lifecycle_facade
from app.bootstrap.system_wiring.nest_session import (
    build_nest_session_services,
    load_emotion_expression_config,
    restore_registered_elfies,
)


def main():
    # Share a container so the Elfie and engine are created in the same thread,
    # avoiding SQLite cross-thread errors.
    engine_holder: dict = {}
    engine_ready = threading.Event()
    lifecycle = create_lifecycle_facade()

    def engine_worker():
        # 1. Assemble services, mirroring the main.py flow in one thread.
        db_path = str(get_db_path())
        ensure_application_storage(db_path)
        model_execution_services = build_model_execution_services(
            db_path,
            live_reload=False,
            resolve_main_food=False,
        )
        nest_session = build_nest_session_services(
            db_path,
            model_execution=model_execution_services.execution,
            godot_ws_port=8765,
            http_port=8000,
            tick_interval_sec=1.5,
        )
        lifecycle.start_runtime_channel(nest_session.world_runtime)
        engine = nest_session.engine
        restore_result = restore_registered_elfies(
            db_path,
            engine.session,
            emotion_expression_config=load_emotion_expression_config(),
        )
        if not restore_result.restored:
            lifecycle.stop_runtime_channel(nest_session.world_runtime)
            raise RuntimeError(
                "No persisted Elfie found; adopt an Elfie before using this script"
            )
        engine_holder["target"] = restore_result.restored[0]
        engine_holder["engine"] = engine
        engine_holder["world_runtime"] = nest_session.world_runtime
        engine_ready.set()
        # 2. Start the blocking engine loop.
        engine.start_loop(
            model_port_factory=nest_session.model_port_factory,
            ticks_to_run=100000,
            interval_sec=3.0,
        )

    engine_thread = threading.Thread(target=engine_worker, daemon=True)
    engine_thread.start()

    # Wait until the engine worker has prepared the engine instance.
    engine_ready.wait(timeout=5.0)
    if "engine" not in engine_holder:
        print("❌ Engine did not become ready within 5 seconds")
        sys.exit(1)
    engine = engine_holder["engine"]
    target = engine_holder["target"]
    time.sleep(2.0)  # Wait for service readiness.

    # 3. Interactive loop.
    print("=" * 60)
    print("🦊 ElfieNest interactive chat")
    print(f"Type a message to chat with {target.name}; type quit/exit/q to exit")
    print("=" * 60)

    while True:
        try:
            user_input = input("\n👤 You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break

        # Send the message to the Elfie.
        engine.session.send_user_message(target.elfie_id, user_input)
        print(f"⏳ {target.name} is thinking...")

    # 4. Cleanup.
    lifecycle.stop_runtime_channel(engine_holder["world_runtime"])


if __name__ == "__main__":
    main()
