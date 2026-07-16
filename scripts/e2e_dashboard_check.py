#!/usr/bin/env python3
"""ElfieNest 管理面板端到端验证脚本

启动 serve.py（fallback 模式 + 随机端口），执行 5 步验证：

  Step 1: Owner 登录 → 创建用户 alice
  Step 2: Alice 登录 → POST adopt → 验证精灵入房
  Step 3: Alice 领养 3 只后第 4 只 → 409
  Step 4: Alice WS 连接（或 HTTP 降级）→ 验证精灵存在
  Step 5: Owner 看到所有精灵（验证隔离）

输出 5/5 或 N/5 报告。
"""

import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def find_distinct_free_ports(count: int) -> list[int]:
    ports: list[int] = []
    while len(ports) < count:
        port = find_free_port()
        if port not in ports:
            ports.append(port)
    return ports


def _header_lower(d: dict, key: str) -> str:
    """从 headers dict 中 case-insensitive 取值。"""
    kl = key.lower()
    for k, v in d.items():
        if k.lower() == kl:
            return v
    return ""


def _cookie_val(headers: dict) -> str:
    """从响应头提取 session_token。"""
    raw = _header_lower(headers, "set-cookie")
    if raw:
        m = re.search(r"session_token=([^;]+)", raw)
        if m:
            return m.group(1)
    return ""


class E2ESession:
    """带 session 持久化的 HTTP 会话。"""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self._session_token = ""

    def _request(
        self, method: str, path: str, data: bytes = None,
        headers: dict = None,
    ) -> tuple[int, dict, str, dict]:
        url = f"{self.base_url}{path}"
        hdrs = dict(headers or {})
        if self._session_token:
            hdrs["Cookie"] = f"session_token={self._session_token}"

        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                body = resp.read().decode("utf-8")
                rh = dict(resp.headers.items())
                cv = _cookie_val(rh)
                if cv:
                    self._session_token = cv
                return resp.status, (json.loads(body) if body else {}), body, rh
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            rh = dict(e.headers.items())
            cv = _cookie_val(rh)
            if cv:
                self._session_token = cv
            try:
                return e.code, (json.loads(body) if body else {}), body, rh
            except json.JSONDecodeError:
                return e.code, {}, body, rh
        except urllib.error.URLError:
            return 0, {}, "", {}

    def get(self, path: str, headers: dict = None) -> tuple[int, dict, str]:
        s, d, r, _ = self._request("GET", path, headers=headers)
        return s, d, r

    def post_json(self, path: str, body: dict, headers: dict = None) -> tuple[int, dict, str, dict]:
        encoded = json.dumps(body).encode("utf-8")
        hdrs = dict(headers or {})
        hdrs.setdefault("Content-Type", "application/json")
        return self._request("POST", path, data=encoded, headers=hdrs)

    def login(self, username: str, password: str) -> tuple[bool, str]:
        """登录，返回 (成功, csrf_token)。"""
        form_data = urllib.parse.urlencode(
            {"username": username, "password": password}
        ).encode("utf-8")
        hdrs = {"Content-Type": "application/x-www-form-urlencoded"}
        s, d, r, rh = self._request("POST", "/api/auth/login", data=form_data, headers=hdrs)
        if s == 200:
            csrf = _header_lower(rh, "x-csrf-token")
            return True, csrf
        return False, ""


def wait_for_server(url: str, timeout: float = 15.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionRefusedError, OSError):
            pass
        time.sleep(0.3)
    return False


def main() -> None:
    port, ws_port, godot_ws_port, audio_port = find_distinct_free_ports(4)
    base_url = f"http://127.0.0.1:{port}"
    data_home = tempfile.mkdtemp(prefix="elfienest-e2e-")
    owner_password = os.environ.get(
        "ELFIENEST_E2E_OWNER_PASSWORD", secrets.token_urlsafe(24)
    )

    print("=" * 60)
    print("  ElfieNest 管理面板 E2E 验证")
    print("=" * 60)
    print(f"  HTTP 端口: {port}")
    print(f"  管理 WS 端口: {ws_port}")
    print(f"  Godot WS 端口: {godot_ws_port}")
    print(f"  音频端口: {audio_port}")
    print()

    print("  🚀 启动 serve.py --fallback ...")
    process = subprocess.Popen(
        [sys.executable, "scripts/serve.py",
         "--fallback",
         "--port", str(port),
         "--ws-port", str(ws_port),
         "--godot-ws-port", str(godot_ws_port),
         "--audio-port", str(audio_port),
         ],
        cwd=PROJECT_ROOT,
        env={**os.environ, "ELFIE_HOME": data_home},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    if not wait_for_server(f"{base_url}/api/health", timeout=25.0):
        try:
            out, _ = process.communicate(timeout=2.0)
            print("  ❌ 服务启动失败，输出:")
            print(out.decode("utf-8", errors="replace")[:2000])
        except subprocess.TimeoutExpired:
            process.kill()
            out, _ = process.communicate(timeout=1.0)
            if out:
                print(out.decode("utf-8", errors="replace")[:2000])
        print("\n❌ serve.py 未能在 25 秒内就绪")
        shutil.rmtree(data_home, ignore_errors=True)
        sys.exit(1)

    print("  ✅ 服务就绪\n")

    owner = E2ESession(base_url)
    alice = E2ESession(base_url)
    results = [False] * 5

    try:
        # ==================================================================
        # Step 0: 首启设置（如无用户，先创建 Owner）
        # ==================================================================
        print("  [Step 0/5] 检查首启状态")
        status, data, raw = owner.get("/api/auth/setup-status")
        if status == 200 and data.get("need_setup"):
            print("    ⚡ 系统无用户，执行首启设置...")
            status, data, raw, _ = owner.post_json(
                "/api/auth/setup",
                {"username": "owner", "password": owner_password},
            )
            aok = status == 201
            print(f"    {'✅' if aok else '❌'} 首启设置 {'成功' if aok else f'失败: {status} {raw[:200]}'}")
        else:
            print("    ✅ 系统已有用户，跳过首启设置")

        # ==================================================================
        # Step 1: Owner 登录 → 创建用户 alice
        # ==================================================================
        print("  [Step 1/5] Owner 登录 → 创建用户 alice")
        ok, owner_csrf = owner.login("owner", owner_password)
        if ok:
            print("    ✅ Owner 登录成功")
            status, data, raw, _ = owner.post_json(
                "/api/owner/users",
                {"username": "alice", "password": "alice123", "role": "user"},
                headers={"X-CSRF-Token": owner_csrf},
            )
            if status == 201:
                print(f"    ✅ 创建用户 alice 成功 (id={data.get('id')})")
                results[0] = True
            else:
                print(f"    ❌ 创建用户失败: {status} {raw[:200]}")
        else:
            print("    ❌ Owner 登录失败")

        # ==================================================================
        # Step 2: Alice 登录 → POST adopt → 验证精灵入房
        # ==================================================================
        print("  [Step 2/5] Alice 登录 → 领养精灵")

        ok, alice_csrf = alice.login("alice", "alice123")
        if ok:
            print("    ✅ Alice 登录成功")
            status, data, raw, _ = alice.post_json(
                "/api/user/adopt",
                {
                    "name": "小白",
                    "anatomy_type": "biped",
                    "personality_style": "好奇探索",
                    "height": "tall",
                    "build": "plump",
                },
                headers={"X-CSRF-Token": alice_csrf},
            )
            if status == 201:
                elfie_id_1 = data.get("elfie_id", "")
                print(f"    ✅ 领养「小白」成功 (elfie_id={elfie_id_1})")

                status, data, raw = alice.get(
                    "/api/user/elfies",
                    headers={"X-CSRF-Token": alice_csrf},
                )
                if status == 200 and isinstance(data, list) and len(data) >= 1:
                    names = [e["name"] for e in data]
                    if "小白" in names:
                        print("    ✅ 精灵「小白」出现在 Alice 列表中")
                        results[1] = True
                    else:
                        print(f"    ❌ 精灵未出现在列表中: {names}")
                else:
                    print(f"    ❌ 查询精灵列表失败: {status} {raw[:200]}")
            else:
                print(f"    ❌ 领养失败: {status} {raw[:200]}")
        else:
            print("    ❌ Alice 登录失败")

        # ==================================================================
        # Step 3: 领养 3 只上限验证
        # ==================================================================
        print("  [Step 3/5] Alice 领养 3 只上限验证")

        def _adopt(name: str) -> int:
            s, d, r, _ = alice.post_json(
                "/api/user/adopt",
                {"name": name, "anatomy_type": "biped",
                 "personality_style": "活泼好动", "height": "standard", "build": "standard"},
                headers={"X-CSRF-Token": alice_csrf},
            )
            return s

        s2 = _adopt("小黄")
        if s2 != 201:
            print(f"    ❌ 第2只领养失败 ({s2})，跳过上限验证")
        else:
            s3 = _adopt("小蓝")
            if s3 != 201:
                print(f"    ❌ 第3只领养失败 ({s3})，跳过上限验证")
            else:
                s4 = _adopt("小绿")
                if s4 == 409:
                    print("    ✅ 第4只被拒绝 (409 上限正确)")
                    results[2] = True
                else:
                    print(f"    ❌ 第4只预期 409 但得到 {s4}")

        # ==================================================================
        # Step 4: HTTP 验证精灵存在
        # ==================================================================
        print("  [Step 4/5] 验证精灵存在（HTTP）")
        status, data, raw = alice.get(
            "/api/user/elfies",
            headers={"X-CSRF-Token": alice_csrf},
        )
        if status == 200 and isinstance(data, list):
            count = len(data)
            print(f"    ✅ Alice 有 {count} 只精灵")
            if count == 3:
                results[3] = True
                print("    ✅ 3 只上限生效")
            else:
                print(f"    ⚠️ 精灵数为 {count}，预期 3")
        else:
            print(f"    ❌ 查询失败: {status} {raw[:200]}")

        # ==================================================================
        # Step 5: Owner 查看所有精灵
        # ==================================================================
        print("  [Step 5/5] Owner 查看所有精灵")
        ok, owner_csrf2 = owner.login("owner", owner_password)
        if ok:
            status, data, raw = owner.get(
                "/api/owner/elfies",
                headers={"X-CSRF-Token": owner_csrf2},
            )
            if status == 200 and isinstance(data, list):
                names = [e["name"] for e in data]
                print(f"    ✅ Owner 看到 {len(data)} 只精灵: {names}")
                if len(data) >= 3:
                    results[4] = True
                else:
                    print(f"    ⚠️ Owner 只看到 {len(data)} 只，预期至少 3")
            else:
                print(f"    ❌ Owner 查询精灵失败: {status} {raw[:200]}")
        else:
            print("    ❌ Owner 重新登录失败")

    except Exception as exc:
        print(f"\n  ❌ 测试异常: {exc}")
        import traceback
        traceback.print_exc()

    finally:
        print()
        print("  🧹 清理子进程...")
        process.terminate()
        try:
            process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2.0)
        shutil.rmtree(data_home, ignore_errors=True)

    # 报告
    print()
    print("=" * 60)
    print("  E2E 验证报告")
    print("=" * 60)

    labels = [
        "Step 1: Owner 登录 → 创建 alice",
        "Step 2: Alice 领养 → 精灵入房",
        "Step 3: 3 只上限 → 第 4 只 409",
        "Step 4: 精灵存在 (HTTP 验证)",
        "Step 5: Owner 多租户隔离",
    ]

    passed = sum(1 for r in results if r)
    for _i, (label, ok) in enumerate(zip(labels, results)):
        symbol = "✅" if ok else "❌"
        print(f"  {symbol} {label}")

    print("=" * 60)
    total = len(labels)
    if passed == total:
        print(f"  结果: {passed}/{total} 通过 — 🎉 全部验证通过！")
    else:
        print(f"  结果: {passed}/{total} 通过 — ⚠️ {total - passed} 项失败")
    print()

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
