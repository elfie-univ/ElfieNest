#!/usr/bin/env python3

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List

from ai_runtime.models.local_profiles import select_local_profile
from ai_runtime.storage.config_store import read_yaml_mapping
from ai_runtime.storage.data_home import get_config_path
from app.features.configuration.runtime_store import write_runtime_config

DEFAULT_LOCAL_PROFILE = select_local_profile(8)
MODELS_TO_PULL = [DEFAULT_LOCAL_PROFILE.text_model, DEFAULT_LOCAL_PROFILE.vision_model]

# 经典大模型预设元数据（多级高中低三档候选库）
PROVIDER_METADATA: Dict[str, Dict[str, Any]] = {
    "openai": {
        "name": "OpenAI Official",
        "api_base": "https://api.openai.com/v1",
        "test_model": "gpt-4o-mini",
        "cheap": {"model": "gpt-4o-mini", "desc": "GPT-4o-Mini (Low energy, fast response)"},
        "deep": {"model": "gpt-4o", "desc": "GPT-4o (Deep reasoning & advanced code)"},
        "multimodal": {"model": "gpt-4o", "desc": "GPT-4o (Native video & audio multimodal)"},
    },
    "deepseek": {
        "name": "DeepSeek Official",
        "api_base": "https://api.deepseek.com/v1",
        "test_model": "deepseek-chat",
        "cheap": {
            "model": "deepseek-chat",
            "desc": "DeepSeek V3 (Excellent cost-performance, strong Chinese)",
        },
        "deep": {
            "model": "deepseek-reasoner",
            "desc": "DeepSeek R1 (Deep thinking & superior logic)",
        },
        "multimodal": {
            "model": "deepseek-chat",
            "desc": "DeepSeek V3 (No native multimodal, using Chat fallback)",
        },
    },
    "gemini": {
        "name": "Google Gemini",
        "api_base": "https://generativelanguage.googleapis.com/v1beta",
        "test_model": "gemini-1.5-flash",
        "cheap": {
            "model": "gemini-1.5-flash",
            "desc": "Gemini 1.5 Flash (Large context, high cost-performance)",
        },
        "deep": {
            "model": "gemini-1.5-pro",
            "desc": "Gemini 1.5 Pro (Top-tier reasoning, ultra-long memory)",
        },
        "multimodal": {
            "model": "gemini-1.5-pro",
            "desc": "Gemini 1.5 Pro (Ultimate multimodal, native audio vision)",
        },
    },
    "qwen": {
        "name": "Alibaba Tongyi Qianwen (DashScope)",
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "test_model": "qwen-coder-turbo",
        "cheap": {
            "model": "qwen-coder-turbo",
            "desc": "Qwen-Coder-Turbo (High-efficiency daily code)",
        },
        "deep": {
            "model": "qwen-coder-plus",
            "desc": "Qwen-Coder-Plus (Strong reasoning professional code)",
        },
        "multimodal": {
            "model": "qwen-vl-plus",
            "desc": "Qwen-VL-Plus (Alibaba native high-quality vision model)",
        },
    },
    "ollama": {
        "name": "Local Ollama (Fully offline)",
        "api_base": "http://localhost:11434",
        "cheap": {"model": "qwen3.5:0.8b", "desc": "Qwen3.5 0.8B (Ultra low energy, instant response)"},
        "deep": {"model": "qwen3.5:4b", "desc": "Qwen3.5 4B (Local moderate reasoning)"},
        "multimodal": {
            "model": "moondream",
            "desc": "Moondream 2 (Local lightweight multimodal vision)",
        },
    },
}


def render_progress_bar(
    completed: int, total: int, prefix: str = "", suffix: str = "", length: int = 40
):
    """Render beautiful streaming progress bar in terminal"""
    if total <= 0:
        return
    percent = float(completed) / total
    filled_length = int(length * percent)
    bar = "█" * filled_length + "░" * (length - filled_length)
    percent_str = f"{percent * 100:.1f}%"

    completed_mb = completed / (1024 * 1024)
    total_mb = total / (1024 * 1024)
    size_info = f"({completed_mb:.1f}MB/{total_mb:.1f}MB)"

    sys.stdout.write(f"\r{prefix} |{bar}| {percent_str} {size_info} {suffix}")
    sys.stdout.flush()


def check_local_ollama_alive() -> bool:
    """Heartbeat check, probe if local 11434 has available Ollama service"""
    url = "http://localhost:11434/api/tags"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=1.5) as response:
            return response.status == 200
    except Exception:
        return False


def pull_ollama_model(model_name: str):
    """Pull model via Ollama HTTP API, render terminal progress bar in real-time"""
    print(f"\n⚡ Preparing to pull compute model: {model_name} ...")
    url = "http://localhost:11434/api/pull"
    payload = {"name": model_name, "stream": True}
    data = json.dumps(payload).encode("utf-8")

    headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req) as response:
            for line in response:
                if not line:
                    continue
                line_data = json.loads(line.decode("utf-8"))

                status = line_data.get("status", "")
                completed = line_data.get("completed", 0)
                total = line_data.get("total", 0)

                if total > 0:
                    render_progress_bar(
                        completed,
                        total,
                        prefix=f"📦 {model_name}",
                        suffix=f"[{status}]",
                    )
                else:
                    sys.stdout.write(f"\r📦 {model_name} | {status}...")
                    sys.stdout.flush()
            print(f"\n✅ Model {model_name} pull/verify successful!")
    except Exception as e:
        print(f"\n❌ Failed to pull model {model_name}: {e}")
        raise e


def test_api_connectivity(provider: str, api_key: str, api_base: str) -> bool:
    """对指定的云端算力服务商发起轻量连通性测试 (Ping)"""
    meta = PROVIDER_METADATA.get(provider)
    if not meta:
        return False

    model_name = meta["test_model"]
    url = f"{api_base}/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    # 极低 Token ping Payload 减少能耗与计费
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5,
    }

    print(f"📡 Proving {meta['name']} physical channel connectivity ({model_name})...")
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=8) as response:
            if response.status == 200:
                print(f"  🟢 Congratulations! {meta['name']} compute handshake successful, response normal!")
                return True
    except Exception as e:
        print(f"  ⚠️  Channel handshake failed. Error details: {e}")
        if isinstance(e, urllib.error.HTTPError):
            try:
                err_body = e.read().decode("utf-8", errors="ignore")
                print(f"     Server feedback: {err_body}")
            except Exception:
                pass
    return False


def setup_code_plan_interactive():
    """Two-step wizard: 1. Activate providers 2. Cross-provider high/mid/low tier binding"""
    print("\n" + "=" * 70)
    print("🎨 Elfie LLM Hybrid Distributed Compute Grid: Personalized Provider & Tier Configuration")
    print("=" * 70)

    # 初始化配置容器
    providers: Dict[str, Dict[str, Any]] = {
        "deepseek": {
            "api_key": "",
            "api_base": PROVIDER_METADATA["deepseek"]["api_base"],
        },
        "openai": {"api_key": "", "api_base": PROVIDER_METADATA["openai"]["api_base"]},
        "gemini": {"api_key": "", "api_base": PROVIDER_METADATA["gemini"]["api_base"]},
        "qwen": {"api_key": "", "api_base": PROVIDER_METADATA["qwen"]["api_base"]},
        "ollama": {"api_key": "", "api_base": PROVIDER_METADATA["ollama"]["api_base"]},
    }

    # 热加载 ELFIE_HOME 下的唯一 YAML 配置；旧 JSON 只允许显式迁移命令读取。
    config_path = get_config_path()
    if config_path.exists():
        try:
            saved = read_yaml_mapping(config_path)
            if "providers" in saved:
                for k, v in saved["providers"].items():
                    if k in providers:
                        providers[k].update(v)
            print("💡 Detected existing configuration, auto-loaded for you.")
        except Exception:
            pass

    # ----------------------------------------------------
    # 阶段一：多厂商订阅激活与密钥配置 (Providers Config)
    # ----------------------------------------------------
    while True:
        print("\n┌────────────────────────────────────────────────────────┐")
        print("│       Elfie 算力订阅源注册中心 (Providers Config)       │")
        print("├────────────────────────────────────────────────────────┤")
        for idx, (p_key, meta) in enumerate(PROVIDER_METADATA.items(), 1):
            status = "🔴 Inactive"
            if p_key == "ollama":
                status = "🟢 Locally managed active"
            elif providers[p_key]["api_key"]:
                status = f"🟢 Active (Key: {providers[p_key]['api_key'][:8]}...)"
            print(f"  {idx}) {meta['name']:<24} [Status: {status}]")
        print("  6) 🆗 订阅配置已就绪，进入下一步高中低端“交配”绑定")
        print("└────────────────────────────────────────────────────────┘")

        choice = input("👉 Select provider to configure [1-6]: ").strip()
        if choice == "6" or not choice:
            break

        p_keys = list(PROVIDER_METADATA.keys())
        if not choice.isdigit() or int(choice) < 1 or int(choice) > 5:
            print("❌ Invalid input, please select again!")
            continue

        selected_provider = p_keys[int(choice) - 1]
        meta = PROVIDER_METADATA[selected_provider]

        if selected_provider == "ollama":
            print("🦊 Local Ollama is a password-free managed service, always active by default!")
            custom_base = input(
                f"   Enter Ollama listen host address [Enter for default: {providers['ollama']['api_base']}]: "
            ).strip()
            if custom_base:
                providers["ollama"]["api_base"] = custom_base
            continue

        print(f"\n🔐 Configuring provider: {meta['name']}")
        key = input("   Enter API Key (empty to disable): ").strip()
        if not key:
            providers[selected_provider]["api_key"] = ""
            print(f"❌ Provider {meta['name']} has been disabled.")
            continue

        base = input(f"   Enter API Base [Enter for recommended default: {meta['api_base']}]: ").strip()
        base_to_save = base if base else meta["api_base"]

        # 开展连通性检测
        success = test_api_connectivity(selected_provider, key, base_to_save)
        if not success:
            ignore = (
                input("   ⚠️  物理连通测试未通过。是否强制保留该配置？(y/n) [默认 n]: ")
                .strip()
                .lower()
            )
            if ignore != "y":
                print("❌ Discarded invalid configuration.")
                continue

        # 保存生效
        providers[selected_provider]["api_key"] = key
        providers[selected_provider]["api_base"] = base_to_save
        print(f"🎉 Provider {meta['name']} configuration saved successfully!")

    # ----------------------------------------------------
    # 阶段二：高中低三档交叉交配绑定 (Cross Mix-and-Match)
    # ----------------------------------------------------
    print("\n" + "=" * 70)
    print("⚙️  阶段二：高中低三档算力与大模型交叉“交配”绑定")
    print("=" * 70)

    # 收集当前已激活的服务商
    active_providers: List[str] = [
        k for k, v in providers.items() if k == "ollama" or v["api_key"]
    ]

    # 构建高中低三档的精选库菜单
    routing: Dict[str, Dict[str, str]] = {"cheap": {}, "deep": {}, "multimodal": {}}

    for tier in ["cheap", "deep", "multimodal"]:
        tier_title = {
            "cheap": "Cheap tier (Low-cost daily assistant, token-efficient, instant response)",
            "deep": "Deep tier (Deep reasoning expert, complex code & math self-evolution tasks)",
            "multimodal": "Multimodal tier (Multimodal expert, multiple images & native audio)",
        }[tier]

        print(f"\n👉 Select your [{tier_title}]:")

        # 提取当前所有激活厂商在该 tier 的默认推荐模型
        candidate_list = []
        for p_key in active_providers:
            meta = PROVIDER_METADATA[p_key]
            model_info = meta[tier]
            candidate_list.append(
                {
                    "provider": p_key,
                    "provider_name": meta["name"],
                    "model": model_info["model"],
                    "desc": model_info["desc"],
                }
            )

        for idx, cand in enumerate(candidate_list, 1):
            print(f"  {idx}) {cand['model']:<24} (from {cand['provider_name']})")
        print(f"  {len(candidate_list) + 1}) ✍️  Manually configure custom model & provider")

        selected_idx = input("Enter option number [default 1]: ").strip()
        if not selected_idx:
            selected_idx = "1"

        if (
            not selected_idx.isdigit()
            or int(selected_idx) < 1
            or int(selected_idx) > len(candidate_list) + 1
        ):
            print("❌ Invalid input, defaulting to option 1.")
            selected_idx = "1"

        idx_val = int(selected_idx)
        if idx_val == len(candidate_list) + 1:
            # 用户自定义输入
            print("   [Manual Custom Model Binding]")
            prov_input = (
                input(
                    "   Enter the model's Provider (e.g., openai, deepseek, qwen, ollama): "
                )
                .strip()
                .lower()
            )
            model_input = input(
                "   Enter the actual model name (e.g., gpt-4o-2024-11-20): "
            ).strip()

            if not prov_input or not model_input:
                print("❌ Input cannot be empty! Falling back to option 1 recommendation.")
                routing[tier] = {
                    "model": candidate_list[0]["model"],
                    "provider": candidate_list[0]["provider"],
                }
            else:
                routing[tier] = {"model": model_input, "provider": prov_input}
        else:
            chosen = candidate_list[idx_val - 1]
            routing[tier] = {"model": chosen["model"], "provider": chosen["provider"]}

        print(
            f"🎯 Successfully bound [{tier} tier] ➡️ Model: '{routing[tier]['model']}' (Provider: {routing[tier]['provider']})"
        )

    # ----------------------------------------------------
    # 数据落盘保存至 json
    # ----------------------------------------------------
    final_config = {
        "providers": providers,
        "cheap_model": routing["cheap"]["model"],
        "cheap_provider": routing["cheap"]["provider"],
        "deep_model": routing["deep"]["model"],
        "deep_provider": routing["deep"]["provider"],
        "multimodal_model": routing["multimodal"]["model"],
        "multimodal_provider": routing["multimodal"]["provider"],
        "ollama_host": providers["ollama"]["api_base"],
    }

    try:
        write_runtime_config(config_path, final_config)

        print("\n" + "=" * 70)
        print("🎉 Congratulations! Cross-provider multi-source compute routing grid configuration complete!")
        print(f"   Configuration saved to ➡️ {config_path}")
        print(
            "   - [Cheap tier]: {} ({})".format(
                final_config["cheap_model"], final_config["cheap_provider"]
            )
        )
        print(
            "   - [Deep  tier]: {} ({})".format(
                final_config["deep_model"], final_config["deep_provider"]
            )
        )
        print(
            "   - [Multi tier]: {} ({})".format(
                final_config["multimodal_model"], final_config["multimodal_provider"]
            )
        )
        print(
            "\n🚀 Now you can launch Elfie neural brain and enjoy high cost-performance distributed hybrid compute!"
        )
        print("=" * 70 + "\n")
    except Exception as e:
        print(f"❌ Failed to persist configuration file: {e}")


def main():
    print("=========================================================================")
    print("🚀 Elfie LLM Runtime Compute Base: One-click Wizard & Model Pull Guide")
    print("=========================================================================")

    # 1. 仅使用用户自行安装的系统级 Ollama；应用不下载私有副本。
    system_ollama = shutil.which("ollama")
    ollama_exec = system_ollama

    if not ollama_exec:
        print("❌ No installed Ollama binary detected locally.")
        print("💡 Please visit official website to install Ollama: https://ollama.com")
        sys.exit(1)

    # 2. 检查 Ollama 服务是否在运行
    service_already_running = check_local_ollama_alive()
    process = None

    if not service_already_running:
        print("🔌 Detected local 11434 compute port not responding. Attempting to start Ollama service in background...")
        try:
            process = subprocess.Popen(
                [ollama_exec, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setpgrp if sys.platform != "win32" else None,
            )
            for _ in range(15):
                time.sleep(1)
                if check_local_ollama_alive():
                    print("✅ Ollama compute service successfully started in background!")
                    break
            else:
                print(
                    "❌ Compute service auto-start timeout! Check if blocked by firewall, or manually run 'ollama serve'."
                )
                if process:
                    process.terminate()
                sys.exit(1)
        except Exception as e:
            print(f"❌ Service process startup exception: {e}")
            sys.exit(1)
    else:
        print("✅ Detected active Ollama compute service process locally.")

    # 3. 逐个拉取本地核心模型
    try:
        for model in MODELS_TO_PULL:
            pull_ollama_model(model)
        print(
            "\n========================================================================="
        )
        print("🎉 Compute base physical environment deployment complete!")
        print("   - Local non-reasoning small model: qwen3.5:0.8b (pulled)")
        print("   - Local peripheral multimodal vision: moondream (pulled)")
        print(
            "========================================================================="
        )

        # 4. 进入跨服务商多源交配配置环节
        setup_code_plan_interactive()

    finally:
        # 回收我们刚刚启动的临时后台服务，保证不残留僵尸进程
        if process:
            print("💤 Recycling temporary bootstrapped local compute service process...")
            process.terminate()
            process.wait()
            print("👋 Temporary service cleanup complete.")


if __name__ == "__main__":
    main()
