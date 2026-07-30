#!/usr/bin/env python3
"""Prepare the optional user-managed Ollama fallback.

Provider connections and food packages are configured through the Owner AI
Runtime workflow. This installer intentionally writes neither configuration.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import urllib.request

from ai_runtime.models.local_profiles import select_local_profile
from ai_runtime.providers.profiles import BUILTIN_PROFILES

DEFAULT_LOCAL_PROFILE = select_local_profile(8)
MODELS_TO_PULL = [DEFAULT_LOCAL_PROFILE.text_model, DEFAULT_LOCAL_PROFILE.vision_model]

_SETUP_PROVIDER_IDS = ("openai", "deepseek", "gemini", "qwen", "ollama")
PROVIDER_METADATA = {
    provider_id: {
        "name": BUILTIN_PROFILES[provider_id].name,
        "api_base": BUILTIN_PROFILES[provider_id].api_base,
        "test_model": BUILTIN_PROFILES[provider_id].test_model,
    }
    for provider_id in _SETUP_PROVIDER_IDS
}


def render_progress_bar(
    completed: int,
    total: int,
    prefix: str = "",
    suffix: str = "",
    length: int = 40,
) -> None:
    if total <= 0:
        return
    percent = float(completed) / total
    filled_length = int(length * percent)
    bar = "#" * filled_length + "." * (length - filled_length)
    completed_mb = completed / (1024 * 1024)
    total_mb = total / (1024 * 1024)
    sys.stdout.write(
        f"\r{prefix} |{bar}| {percent * 100:.1f}% "
        f"({completed_mb:.1f}MB/{total_mb:.1f}MB) {suffix}"
    )
    sys.stdout.flush()


def check_local_ollama_alive() -> bool:
    try:
        request = urllib.request.Request(
            "http://localhost:11434/api/tags",
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=1.5) as response:
            return response.status == 200
    except Exception:
        return False


def pull_ollama_model(model_name: str) -> None:
    print(f"\nPreparing local model: {model_name}")
    request = urllib.request.Request(
        "http://localhost:11434/api/pull",
        data=json.dumps({"name": model_name, "stream": True}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        for line in response:
            if not line:
                continue
            event = json.loads(line.decode("utf-8"))
            total = int(event.get("total", 0))
            if total:
                render_progress_bar(
                    int(event.get("completed", 0)),
                    total,
                    prefix=model_name,
                    suffix=str(event.get("status", "")),
                )
    print(f"\nLocal model ready: {model_name}")


def main() -> None:
    executable = shutil.which("ollama")
    if not executable:
        print("Ollama is not installed. Install it from https://ollama.com")
        raise SystemExit(1)

    started_process: subprocess.Popen[bytes] | None = None
    if not check_local_ollama_alive():
        started_process = subprocess.Popen(
            [executable, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(20):
            if check_local_ollama_alive():
                break
            time.sleep(0.5)
        else:
            started_process.terminate()
            print("Ollama did not become ready.")
            raise SystemExit(1)

    try:
        for model_name in MODELS_TO_PULL:
            pull_ollama_model(model_name)
        print(
            "\nOllama preparation is complete. Configure Provider connections and "
            "food packages in the Owner AI Runtime page."
        )
    finally:
        if started_process is not None:
            started_process.terminate()
            started_process.wait()


if __name__ == "__main__":
    main()
