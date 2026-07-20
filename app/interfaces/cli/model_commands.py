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
    print("\n  📦 模型目录\n")

    config = read_user_config()

    print(f"  {'模型ID':<35s} {'能力':<25s} {'费用等级':<8s} {'状态':<8s}")
    print("  " + "-" * 85)

    for row in list_model_rows(config):
        print(
            f"  {row.model_id:<35s} {row.capabilities_text:<25s} "
            f"{row.cost_text:<8s} {row.status_text:<8s}"
        )

    print()


def scan_models() -> None:
    print("\n  🔍 扫描 Ollama 本地模型...\n")

    try:
        resp = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5.0)
        data = json.loads(resp.read().decode())
    except urllib.error.URLError:
        print("  ❌ Ollama 未运行")
        print("  💡 启动 Ollama: ollama serve")
        print()
        return
    except (OSError, TimeoutError, json.JSONDecodeError) as e:
        print(f"  ❌ 扫描失败: {e}")
        print()
        return

    models = data.get("models", [])
    if not models:
        print("  ⚠️  Ollama 中没有模型")
        print("  💡 使用 'ollama pull qwen3.5:0.8b' 下载模型")
        return

    print(f"  发现 {len(models)} 个本地模型:\n")
    print(f"  {'模型名称':<30s} {'大小':<12s} {'修改时间'}")
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

    print("\n  ✅ Ollama 模型已列出")
    print()
