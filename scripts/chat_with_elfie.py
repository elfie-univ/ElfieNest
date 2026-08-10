#!/usr/bin/env python3
"""ElfieNest interactive chat client.

Starts the full service stack so the user can chat with Elfie "Aifei" in the terminal.
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

from ai_runtime import LLMRuntimeConfig, RuntimeAgent
from ai_runtime.storage.data_home import get_db_path
from app.bootstrap.lifecycle import create_lifecycle_facade
from app.bootstrap.nest_session import build_nest_session_services
from elfie import ElfieFactory
from infrastructure.persistence.food_catalog import SQLiteFoodPackageRepository
from infrastructure.persistence.store import init_db


def main():
    # Share a container so the Elfie and engine are created in the same thread,
    # avoiding SQLite cross-thread errors.
    engine_holder: dict = {}
    engine_ready = threading.Event()
    lifecycle = create_lifecycle_facade()

    def engine_worker():
        # 1. Assemble services, mirroring the main.py flow in one thread.
        config = LLMRuntimeConfig(ollama_host="http://localhost:11434")
        db_path = str(get_db_path())
        init_db(db_path)
        food_repository = SQLiteFoodPackageRepository(db_path)
        runtime_agent = RuntimeAgent(
            config,
            food_catalog_repository=food_repository,
        )
        nest_session = build_nest_session_services(
            db_path,
            runtime=runtime_agent,
            godot_ws_port=8765,
            http_port=8000,
            tick_interval_sec=1.5,
        )
        lifecycle.start_runtime_channel(nest_session.world_runtime)
        engine = nest_session.engine
        elfie = ElfieFactory().create(
            elfie_id="Aifei",
            godot_api=nest_session.world_runtime,
        )
        engine.session.register_elfie("Aifei", elfie)
        engine_holder["engine"] = engine
        engine_holder["world_runtime"] = nest_session.world_runtime
        engine_ready.set()
        # 2. Start the blocking engine loop.
        engine.start_loop(
            runtime_factory=nest_session.runtime_factory,
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
    time.sleep(2.0)  # Wait for service readiness.

    # 3. Interactive loop.
    print("=" * 60)
    print("🦊 ElfieNest interactive chat")
    print("Type a message to chat with Aifei; type quit/exit/q to exit")
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
        engine.session.send_user_message("Aifei", user_input)
        print("⏳ Aifei is thinking...")

    # 4. Cleanup.
    lifecycle.stop_runtime_channel(engine_holder["world_runtime"])


if __name__ == "__main__":
    main()
