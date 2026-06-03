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

# 项目基准路径
RUNTIME_DIR = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.join(RUNTIME_DIR, "bin")
OLLAMA_PATH = os.path.join(BIN_DIR, "ollama")

# 默认本地待拉取模型清单
MODELS_TO_PULL = ["qwen3.5:0.8b", "moondream"]

# 经典大模型预设元数据（多级高中低三档候选库）
PROVIDER_METADATA: Dict[str, Dict[str, Any]] = {
    "openai": {
        "name": "OpenAI 官方",
        "api_base": "https://api.openai.com/v1",
        "test_model": "gpt-4o-mini",
        "cheap": {"model": "gpt-4o-mini", "desc": "GPT-4o-Mini (低能耗，极速响应)"},
        "deep": {"model": "gpt-4o", "desc": "GPT-4o (深度推理与高级代码)"},
        "multimodal": {"model": "gpt-4o", "desc": "GPT-4o (原生视频与音频多模态)"},
    },
    "deepseek": {
        "name": "DeepSeek 官方",
        "api_base": "https://api.deepseek.com/v1",
        "test_model": "deepseek-chat",
        "cheap": {
            "model": "deepseek-chat",
            "desc": "DeepSeek V3 (极佳性价比，极强中文)",
        },
        "deep": {
            "model": "deepseek-reasoner",
            "desc": "DeepSeek R1 (深度思考与超强逻辑)",
        },
        "multimodal": {
            "model": "deepseek-chat",
            "desc": "DeepSeek V3 (无原生多模态，以 Chat 替代)",
        },
    },
    "gemini": {
        "name": "Google Gemini",
        "api_base": "https://generativelanguage.googleapis.com/v1beta",
        "test_model": "gemini-1.5-flash",
        "cheap": {
            "model": "gemini-1.5-flash",
            "desc": "Gemini 1.5 Flash (大上下文，高性价比)",
        },
        "deep": {
            "model": "gemini-1.5-pro",
            "desc": "Gemini 1.5 Pro (殿堂级推理，超长记忆)",
        },
        "multimodal": {
            "model": "gemini-1.5-pro",
            "desc": "Gemini 1.5 Pro (极致多模态，原生听觉视觉)",
        },
    },
    "qwen": {
        "name": "阿里通义千问 (DashScope)",
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "test_model": "qwen-coder-turbo",
        "cheap": {
            "model": "qwen-coder-turbo",
            "desc": "Qwen-Coder-Turbo (高能效代码日常)",
        },
        "deep": {
            "model": "qwen-coder-plus",
            "desc": "Qwen-Coder-Plus (强推理专业级代码)",
        },
        "multimodal": {
            "model": "qwen-vl-plus",
            "desc": "Qwen-VL-Plus (阿里原生高画质视觉模型)",
        },
    },
    "ollama": {
        "name": "本地 Ollama (完全离线)",
        "api_base": "http://localhost:11434",
        "cheap": {"model": "qwen3.5:0.8b", "desc": "Qwen3.5 0.8B (超省能耗，秒级回复)"},
        "deep": {"model": "qwen3.5:4b", "desc": "Qwen3.5 4B (本地中度推理)"},
        "multimodal": {
            "model": "moondream",
            "desc": "Moondream 2 (本地轻量多模态视觉)",
        },
    },
}


def render_progress_bar(
    completed: int, total: int, prefix: str = "", suffix: str = "", length: int = 40
):
    """在终端渲染精美的流式进度条"""
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


def ensure_bin_dir():
    """保证 bin 目录存在"""
    if not os.path.exists(BIN_DIR):
        os.makedirs(BIN_DIR)


def download_ollama_macos() -> bool:
    """在 macOS 环境下静默下载官方的 Ollama CLI 二进制文件"""
    if os.path.exists(OLLAMA_PATH):
        print(f"✅ 检测到 Ollama 二进制已存在于本地: {OLLAMA_PATH}")
        return True

    if sys.platform != "darwin":
        print(f"❌ 自动下载仅支持 macOS (Darwin) 系统，当前系统为 {sys.platform}。")
        print("💡 请前往 Ollama 官网 (https://ollama.com) 手动下载安装并保持服务运行。")
        return False

    print("🦊 正在为您的 macOS 静默下载轻量级 Ollama 命令行底座...")
    download_url = "https://ollama.com/download/ollama-darwin"

    ensure_bin_dir()

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        req = urllib.request.Request(download_url, headers=headers)
        with urllib.request.urlopen(req) as response:
            total_size = int(response.info().get("Content-Length", 0))
            downloaded = 0
            block_size = 1024 * 256  # 256KB

            with open(OLLAMA_PATH, "wb") as f:
                while True:
                    buffer = response.read(block_size)
                    if not buffer:
                        break
                    downloaded += len(buffer)
                    f.write(buffer)
                    render_progress_bar(
                        downloaded,
                        total_size,
                        prefix="📥 下载底座",
                        suffix="正在写入...",
                    )

        print("\n🎉 下载完成！正在赋予其可执行权限...")
        os.chmod(OLLAMA_PATH, 0o755)
        print("✅ Ollama 底座执行权限配置完毕。")
        return True
    except Exception as e:
        print(f"\n❌ 下载 Ollama 发生致命异常: {e}")
        if os.path.exists(OLLAMA_PATH):
            try:
                os.remove(OLLAMA_PATH)
            except Exception:
                pass
        return False


def check_local_ollama_alive() -> bool:
    """心跳检测，探测本地 11434 是否已经有可用的 Ollama 服务"""
    url = "http://localhost:11434/api/tags"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=1.5) as response:
            return response.status == 200
    except Exception:
        return False


def pull_ollama_model(model_name: str):
    """通过 Ollama HTTP API 拉取模型，并实时渲染终端进度条"""
    print(f"\n⚡ 准备拉取算力模型: {model_name} ...")
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
            print(f"\n✅ 模型 {model_name} 拉取/校验成功！")
    except Exception as e:
        print(f"\n❌ 拉取模型 {model_name} 失败: {e}")
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

    print(f"📡 正在探测 {meta['name']} 的物理通道连通性 ({model_name})...")
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=8) as response:
            if response.status == 200:
                print(f"  🟢 恭喜！{meta['name']} 算力握手成功，响应一切正常！")
                return True
    except Exception as e:
        print(f"  ⚠️  通道握手未通过。错误详情: {e}")
        if isinstance(e, urllib.error.HTTPError):
            try:
                err_body = e.read().decode("utf-8", errors="ignore")
                print(f"     服务端反馈: {err_body}")
            except Exception:
                pass
    return False


def setup_code_plan_interactive():
    """两步法极炫引导程序：1. 激活订阅源 2. 跨源高中低档交配绑定"""
    print("\n" + "=" * 70)
    print("🎨 Elfie LLM 混合分布式算力网格：个性化订阅与高中低交配配置")
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

    # 热加载已有配置
    json_path = os.path.join(RUNTIME_DIR, "runtime_config.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, encoding="utf-8") as f:
                saved = json.load(f)
            if "providers" in saved:
                for k, v in saved["providers"].items():
                    if k in providers:
                        providers[k].update(v)
            print("💡 检测到已有历史配置，已为您自动预载入。")
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
            status = "🔴 未激活"
            if p_key == "ollama":
                status = "🟢 本地全托管激活"
            elif providers[p_key]["api_key"]:
                status = f"🟢 已激活 (Key: {providers[p_key]['api_key'][:8]}...)"
            print(f"  {idx}) {meta['name']:<24} [状态: {status}]")
        print("  6) 🆗 订阅配置已就绪，进入下一步高中低端“交配”绑定")
        print("└────────────────────────────────────────────────────────┘")

        choice = input("👉 请选择要配置的订阅源编号 [1-6]: ").strip()
        if choice == "6" or not choice:
            break

        p_keys = list(PROVIDER_METADATA.keys())
        if not choice.isdigit() or int(choice) < 1 or int(choice) > 5:
            print("❌ 编号输入错误，请重新选择！")
            continue

        selected_provider = p_keys[int(choice) - 1]
        meta = PROVIDER_METADATA[selected_provider]

        if selected_provider == "ollama":
            print("🦊 本地 Ollama 算力属于免密托管服务，默认长驻激活！")
            custom_base = input(
                f"   请输入 Ollama 监听主机地址 [回车默认: {providers['ollama']['api_base']}]: "
            ).strip()
            if custom_base:
                providers["ollama"]["api_base"] = custom_base
            continue

        print(f"\n🔐 正在配置服务商: {meta['name']}")
        key = input("   请输入 API Key (空值代表不启用): ").strip()
        if not key:
            providers[selected_provider]["api_key"] = ""
            print(f"❌ 已将服务商 {meta['name']} 设为禁用状态。")
            continue

        base = input(f"   请输入 API Base [回车默认推荐: {meta['api_base']}]: ").strip()
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
                print("❌ 已放弃保存该无效配置。")
                continue

        # 保存生效
        providers[selected_provider]["api_key"] = key
        providers[selected_provider]["api_base"] = base_to_save
        print(f"🎉 服务商 {meta['name']} 配置保存成功！")

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
            "cheap": "Cheap 档（低耗日常助理，主要节省 Token，要求秒回）",
            "deep": "Deep 档（深度推理专家，主要处理复杂代码、数学自进化任务）",
            "multimodal": "Multimodal 档（多模态专家，主要处理多张图片与原生音频）",
        }[tier]

        print(f"\n👉 请选择您的【{tier_title}】:")

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
            print(f"  {idx}) {cand['model']:<24} (来自 {cand['provider_name']})")
        print(f"  {len(candidate_list) + 1}) ✍️  手动配置自定义模型与服务商")

        selected_idx = input("请输入选项编号 [默认 1]: ").strip()
        if not selected_idx:
            selected_idx = "1"

        if (
            not selected_idx.isdigit()
            or int(selected_idx) < 1
            or int(selected_idx) > len(candidate_list) + 1
        ):
            print("❌ 输入有误，默认回车为您绑定第 1 项。")
            selected_idx = "1"

        idx_val = int(selected_idx)
        if idx_val == len(candidate_list) + 1:
            # 用户自定义输入
            print("   【手动自定义模型绑定】")
            prov_input = (
                input(
                    "   请输入该模型的归属 Provider (如 openai, deepseek, qwen, ollama): "
                )
                .strip()
                .lower()
            )
            model_input = input(
                "   请输入该模型的真实大模型名称 (如 gpt-4o-2024-11-20): "
            ).strip()

            if not prov_input or not model_input:
                print("❌ 输入不可为空！被迫退回并默认绑定第 1 项推荐。")
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
            f"🎯 成功绑定【{tier} 档】 ➡️ 模型: '{routing[tier]['model']}' (Provider: {routing[tier]['provider']})"
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
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(final_config, f, indent=4, ensure_ascii=False)

        print("\n" + "=" * 70)
        print("🎉 恭喜！跨服务商多源算力混配路由网格配置已大功告成！")
        print(f"   配置文件已成功落盘 ➡️ {json_path}")
        print(
            "   - 【Cheap 档】: {} ({})".format(
                final_config["cheap_model"], final_config["cheap_provider"]
            )
        )
        print(
            "   - 【Deep  档】: {} ({})".format(
                final_config["deep_model"], final_config["deep_provider"]
            )
        )
        print(
            "   - 【Multi 档】: {} ({})".format(
                final_config["multimodal_model"], final_config["multimodal_provider"]
            )
        )
        print(
            "\n🚀 现在，您可以愉快地拉起 Elfie 神经大脑，尽享高性价比分布式混合算力的畅快！"
        )
        print("=" * 70 + "\n")
    except Exception as e:
        print(f"❌ 持久化配置文件落盘失败: {e}")


def main():
    print("=========================================================================")
    print("🚀 Elfie LLM Runtime 算力底座：一键引导与模型拉取引导程序")
    print("=========================================================================")

    # 1. 确保 Ollama CLI 存在
    _ = download_ollama_macos()

    # 检查系统自带的 ollama
    system_ollama = shutil.which("ollama")
    ollama_exec = OLLAMA_PATH if os.path.exists(OLLAMA_PATH) else system_ollama

    if not ollama_exec:
        print(
            "❌ 本地未检测到已安装的 Ollama 二进制，且非 macOS 系统无法自动托管下载。"
        )
        print("💡 请前往官网手动安装 Ollama：https://ollama.com")
        sys.exit(1)

    # 2. 检查 Ollama 服务是否在运行
    service_already_running = check_local_ollama_alive()
    process = None

    if not service_already_running:
        print("🔌 检测到本地 11434 算力端口未响应。尝试在后台拉起 Ollama 服务...")
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
                    print("✅ Ollama 算力服务已在后台成功拉起！")
                    break
            else:
                print(
                    "❌ 算力服务自启动超时！请检查本地是否被防火墙阻拦，或手动运行 'ollama serve'。"
                )
                if process:
                    process.terminate()
                sys.exit(1)
        except Exception as e:
            print(f"❌ 启动服务进程异常: {e}")
            sys.exit(1)
    else:
        print("✅ 检测到本地已存在活跃的 Ollama 算力服务进程。")

    # 3. 逐个拉取本地核心模型
    try:
        for model in MODELS_TO_PULL:
            pull_ollama_model(model)
        print(
            "\n========================================================================="
        )
        print("🎉 算力底座物理环境部署完毕！")
        print("   - 本地非思考小模型: qwen3.5:0.8b (已拉取)")
        print("   - 本地余光多模态视觉: moondream (已拉取)")
        print(
            "========================================================================="
        )

        # 4. 进入跨服务商多源交配配置环节
        setup_code_plan_interactive()

    finally:
        # 回收我们刚刚启动的临时后台服务，保证不残留僵尸进程
        if process:
            print("💤 正在回收临时引导的本地算力服务进程...")
            process.terminate()
            process.wait()
            print("👋 临时服务回收完毕。")


if __name__ == "__main__":
    main()
