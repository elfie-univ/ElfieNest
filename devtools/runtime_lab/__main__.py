"""Runtime 开发配置与连接测试命令行。"""

import argparse
import getpass
import sys
from typing import Any, Dict

from devtools.runtime_lab.config_store import (
    PROVIDER_DEFAULTS,
    RuntimeLabConfigStore,
)
from runtime.gateway.llm_api import call_llm_api


def _configure(store: RuntimeLabConfigStore, args: argparse.Namespace) -> int:
    current = store.status()
    provider = (args.provider or input("服务商 [ollama]: ").strip() or "ollama").lower()
    if provider not in PROVIDER_DEFAULTS:
        print(f"不支持的服务商: {provider}", file=sys.stderr)
        return 2
    defaults = current["providers"].get(provider, PROVIDER_DEFAULTS[provider])
    api_base = (
        args.api_base
        or input(f"API Base [{defaults['api_base']}]: ").strip()
        or str(defaults["api_base"])
    )
    api_mode = (
        args.api_mode
        or input(f"API 模式 [{defaults['api_mode']}]: ").strip()
        or str(defaults["api_mode"])
    )
    model = (
        args.model
        or input(f"测试模型 [{defaults['test_model']}]: ").strip()
        or str(defaults["test_model"])
    )
    default_key = "local_fast" if provider == "ollama" else "remote_deep"
    model_key = (
        args.model_key
        or input(f"精灵实验模型槽位 [{default_key}]: ").strip()
        or default_key
    )
    api_key = None
    if provider != "ollama" and (args.prompt_key or args.provider is None):
        api_key = getpass.getpass("API Key（隐藏输入；留空则删除开发密钥）: ")
    status = store.configure_provider(
        provider,
        api_base=api_base,
        api_mode=api_mode,
        model=model,
        model_key=model_key,
        api_key=api_key,
    )
    print(
        f"已保存开发配置：{status['provider']}/{status['model']} "
        f"({status['model_key']})"
    )
    print(f"配置目录：{status['config_dir']}")
    return 0


def _show(store: RuntimeLabConfigStore) -> int:
    status = store.status()
    ready = "可尝试连接" if status["ready_for_attempt"] else "缺少开发密钥"
    print("Runtime 开发配置（与正式运行隔离）")
    print(f"当前模型：{status['provider']}/{status['model']} [{status['model_key']}]")
    print(f"状态：{ready}")
    print(f"配置：{status['config_path']}")
    print(f"密钥：{status['secrets_path']}（内容不显示）")
    print("\n服务商：")
    for name, info in status["providers"].items():
        marker = "已配置" if info["credential_configured"] else "未配置"
        print(f"  {name:<14} {marker:<4} {info['test_model']}")
    return 0


def _test_one(
    store: RuntimeLabConfigStore, provider: str, message: str
) -> Dict[str, Any]:
    config = store.load_runtime_config()
    info = config.providers.get(provider)
    if info is None:
        raise ValueError(f"未知服务商: {provider}")
    model = str(info.get("test_model") or "")
    if not model:
        raise ValueError(f"服务商 {provider} 尚未配置测试模型")
    if provider != "ollama" and not info.get("api_key"):
        raise ValueError(f"服务商 {provider} 尚未配置开发 API Key")
    started = __import__("time").perf_counter()
    text = call_llm_api(
        config,
        provider,
        model,
        [{"role": "user", "content": message}],
        config.temperature,
        min(config.max_tokens, 256),
    )
    duration_ms = round((__import__("time").perf_counter() - started) * 1000, 2)
    return {
        "provider": provider,
        "model": model,
        "text": text,
        "duration_ms": duration_ms,
    }


def _test(store: RuntimeLabConfigStore, args: argparse.Namespace) -> int:
    status = store.status()
    providers = (
        [
            name
            for name, info in status["providers"].items()
            if info["credential_configured"]
        ]
        if args.all
        else [args.provider or status["provider"]]
    )
    failed = False
    for provider in providers:
        try:
            result = _test_one(store, provider, args.message)
            print(f"✓ {provider}/{result['model']} · {result['duration_ms']} ms")
            print(result["text"])
        except Exception as exc:
            failed = True
            print(f"✗ {provider}: {type(exc).__name__}: {exc}", file=sys.stderr)
    return 1 if failed else 0


def _chat(store: RuntimeLabConfigStore, args: argparse.Namespace) -> int:
    provider = args.provider or store.status()["provider"]
    print(f"正在使用 {provider}。输入 /exit 退出。")
    while True:
        try:
            message = input("你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if message in {"/exit", "/quit"}:
            return 0
        if not message:
            continue
        try:
            result = _test_one(store, provider, message)
            print(f"模型> {result['text']}\n")
        except Exception as exc:
            print(f"连接失败：{type(exc).__name__}: {exc}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="配置并测试独立的开发 Runtime")
    parser.add_argument("--config-dir", default=None, help="覆盖开发配置目录")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("show", help="查看脱敏后的开发配置状态")
    configure = subparsers.add_parser("configure", help="配置一个模型连接")
    configure.add_argument("--provider", choices=sorted(PROVIDER_DEFAULTS))
    configure.add_argument("--api-base")
    configure.add_argument(
        "--api-mode", choices=["ollama", "chat_completions", "anthropic_messages"]
    )
    configure.add_argument("--model")
    configure.add_argument(
        "--model-key",
        choices=["local_fast", "remote_cheap", "remote_deep", "remote_multimodal"],
    )
    configure.add_argument(
        "--prompt-key", action="store_true", help="使用隐藏输入保存开发 API Key"
    )

    test = subparsers.add_parser("test", help="发送一条消息验证连接")
    test.add_argument("--provider", choices=sorted(PROVIDER_DEFAULTS))
    test.add_argument("--all", action="store_true", help="测试全部已配置连接")
    test.add_argument("--message", default="请只回复：连接成功")

    chat = subparsers.add_parser("chat", help="进入简单文字对话测试")
    chat.add_argument("--provider", choices=sorted(PROVIDER_DEFAULTS))

    args = parser.parse_args()
    store = RuntimeLabConfigStore(args.config_dir)
    if args.command == "show":
        return _show(store)
    if args.command == "configure":
        return _configure(store, args)
    if args.command == "test":
        return _test(store, args)
    return _chat(store, args)


if __name__ == "__main__":
    raise SystemExit(main())
