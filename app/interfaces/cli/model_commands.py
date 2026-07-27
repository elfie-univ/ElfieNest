from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional

from app.features.configuration.provider_service import list_model_rows
from app.features.configuration.user_config import read_user_config


def dispatch_models(subcmd: Optional[str]) -> None:
    command = subcmd or "list"
    if command == "list":
        list_models()
    elif command == "scan":
        scan_models()


def list_models() -> None:
    print("\n  📦 Model Catalog\n")

    config = read_user_config()

    print(f"  {'Model ID':<35s} {'Capabilities':<25s} {'Cost':<8s} {'Status':<8s}")
    print("  " + "-" * 85)

    for row in list_model_rows(config):
        print(
            f"  {row.model_id:<35s} {row.capabilities_text:<25s} "
            f"{row.cost_text:<8s} {row.status_text:<8s}"
        )

    print()


def scan_models() -> None:
    print("\n  🔍 Scanning Ollama local models...\n")

    try:
        resp = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5.0)
        data = json.loads(resp.read().decode())
    except urllib.error.URLError:
        print("  ❌ Ollama not running")
        print("  💡 Start Ollama: ollama serve")
        print()
        return
    except (OSError, TimeoutError, json.JSONDecodeError) as e:
        print(f"  ❌ Scan failed: {e}")
        print()
        return

    models = data.get("models", [])
    if not models:
        print("  ⚠️  No models in Ollama")
        print("  💡 Use 'ollama pull qwen3.5:0.8b' to download a model")
        return

    print(f"  Found {len(models)} local models:\n")
    print(f"  {'Model Name':<30s} {'Size':<12s} {'Modified'}")
    print("  " + "-" * 70)

    for model in models:
        name = model.get("name", "")
        size_bytes = model.get("size", 0)
        size_gb = size_bytes / (1024**3)
        modified = model.get("modified_at", "")
        if size_gb >= 1:
            size_str = f"{size_gb:.1f} GB"
        else:
            size_mb = size_bytes / (1024**2)
            size_str = f"{size_mb:.0f} MB"

        print(f"  {name:<30s} {size_str:<12s} {modified}")

    print("\n  ✅ Ollama models listed")
    print()
