#!/usr/bin/env python3
"""ElfieNest management dashboard end-to-end verification script.

Starts serve.py in fallback mode on random ports, then runs five checks:

  Step 1: Owner login -> create user alice
  Step 2: Alice login -> complete the adoption journey -> verify Elfie appears
  Step 3: Alice adopts 3 Elfies, then the 4th request returns 409
  Step 4: Verify Elfies via HTTP
  Step 5: Owner can see all Elfies, proving owner visibility

Prints a 5/5 or N/5 report.
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
    """Read a header value from a dict case-insensitively."""
    kl = key.lower()
    for k, v in d.items():
        if k.lower() == kl:
            return v
    return ""


def _cookie_val(headers: dict) -> str:
    """Extract session_token from response headers."""
    raw = _header_lower(headers, "set-cookie")
    if raw:
        m = re.search(r"session_token=([^;]+)", raw)
        if m:
            return m.group(1)
    return ""


class E2ESession:
    """HTTP session with cookie persistence."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self._session_token = ""

    def _request(
        self,
        method: str,
        path: str,
        data: bytes = None,
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

    def post_json(
        self, path: str, body: dict, headers: dict = None
    ) -> tuple[int, dict, str, dict]:
        encoded = json.dumps(body).encode("utf-8")
        hdrs = dict(headers or {})
        hdrs.setdefault("Content-Type", "application/json")
        return self._request("POST", path, data=encoded, headers=hdrs)

    def login(self, account_id: str, password: str) -> tuple[bool, str]:
        """Log in and return (success, csrf_token)."""
        form_data = urllib.parse.urlencode(
            {"account_id": account_id, "password": password}
        ).encode("utf-8")
        hdrs = {"Content-Type": "application/x-www-form-urlencoded"}
        s, d, r, rh = self._request(
            "POST", "/api/v1/auth/login", data=form_data, headers=hdrs
        )
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
    port, ws_port, godot_ws_port = find_distinct_free_ports(3)
    base_url = f"http://127.0.0.1:{port}"
    data_home = tempfile.mkdtemp(prefix="elfienest-e2e-")
    owner_password = os.environ.get(
        "ELFIENEST_E2E_OWNER_PASSWORD", secrets.token_urlsafe(24)
    )

    print("=" * 60)
    print("  ElfieNest management dashboard E2E verification")
    print("=" * 60)
    print(f"  HTTP port: {port}")
    print(f"  Management WS port: {ws_port}")
    print(f"  Godot WS port: {godot_ws_port}")
    print()

    print("  🚀 Starting serve.py --fallback ...")
    process = subprocess.Popen(
        [
            sys.executable,
            "scripts/serve.py",
            "--fallback",
            "--port",
            str(port),
            "--ws-port",
            str(ws_port),
            "--godot-ws-port",
            str(godot_ws_port),
        ],
        cwd=PROJECT_ROOT,
        env={**os.environ, "ELFIE_HOME": data_home},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    if not wait_for_server(f"{base_url}/api/health", timeout=25.0):
        try:
            out, _ = process.communicate(timeout=2.0)
            print("  ❌ Service failed to start; output:")
            print(out.decode("utf-8", errors="replace")[:2000])
        except subprocess.TimeoutExpired:
            process.kill()
            out, _ = process.communicate(timeout=1.0)
            if out:
                print(out.decode("utf-8", errors="replace")[:2000])
        print("\n❌ serve.py did not become ready within 25 seconds")
        shutil.rmtree(data_home, ignore_errors=True)
        sys.exit(1)

    print("  ✅ Service is ready\n")

    owner = E2ESession(base_url)
    alice = E2ESession(base_url)
    results = [False] * 5

    try:
        # ==================================================================
        # Step 0: First-run setup; create Owner if no user exists.
        # ==================================================================
        print("  [Step 0/5] Checking first-run setup state")
        status, data, raw = owner.get("/api/auth/setup-status")
        if status == 200 and data.get("need_setup"):
            print("    ⚡ No users exist; running first-run setup...")
            status, data, raw, _ = owner.post_json(
                "/api/auth/setup",
                {"account_id": "owner", "password": owner_password},
            )
            aok = status == 201
            print(
                f"    {'✅' if aok else '❌'} First-run setup {'succeeded' if aok else f'failed: {status} {raw[:200]}'}"
            )
        else:
            print("    ✅ Users already exist; skipping first-run setup")

        # ==================================================================
        # Step 1: Owner login -> create user alice.
        # ==================================================================
        print("  [Step 1/5] Owner login -> create user alice")
        ok, owner_csrf = owner.login("owner", owner_password)
        if ok:
            print("    ✅ Owner login succeeded")
            status, data, raw, _ = owner.post_json(
                "/api/v1/admin/users",
                {"account_id": "alice", "password": "alice123", "role": "user"},
                headers={"X-CSRF-Token": owner_csrf},
            )
            if status == 201:
                print(f"    ✅ Created user alice (id={data.get('user_id')})")
                results[0] = True
            else:
                print(f"    ❌ Failed to create user: {status} {raw[:200]}")
        else:
            print("    ❌ Owner login failed")

        # ==================================================================
        # Step 2: Alice login -> complete adoption journey -> verify Elfie appears.
        # ==================================================================
        print("  [Step 2/5] Alice login -> adopt an Elfie")

        ok, alice_csrf = alice.login("alice", "alice123")

        def _adopt(name: str) -> tuple[int, dict, str]:
            status, candidates, raw, _ = alice.post_json(
                "/api/user/adoption/candidates",
                {
                    "species_id": "fox",
                    "life_stage": "young_adult",
                    "gender": "any",
                    "appearance": {
                        "stature": "standard",
                        "build": "standard",
                        "face": "soft",
                        "signature": "warm",
                        "priority": "face",
                    },
                    "answers": ["quiet", "research", "plan", "discuss", "steady"],
                },
                headers={"X-CSRF-Token": alice_csrf},
            )
            if status != 200:
                return status, candidates, raw
            candidate_ids = [
                item["candidate_id"] for item in candidates["candidates"][:2]
            ]
            status, replies, raw, _ = alice.post_json(
                "/api/user/adoption/replies",
                {
                    "candidate_set_id": candidates["candidate_set_id"],
                    "candidate_ids": candidate_ids,
                },
                headers={"X-CSRF-Token": alice_csrf},
            )
            if status != 200:
                return status, replies, raw
            accepted = next(
                (
                    reply
                    for reply in replies["replies"]
                    if reply["status"] == "accepted"
                ),
                None,
            )
            if accepted is None:
                return 409, {}, "No candidate accepted the invitation"
            status, adopted, raw, _ = alice.post_json(
                "/api/user/adoption/commit",
                {
                    "candidate_set_id": candidates["candidate_set_id"],
                    "candidate_id": accepted["candidate_id"],
                    "name": name,
                },
                headers={"X-CSRF-Token": alice_csrf},
            )
            return status, adopted, raw

        if ok:
            print("    ✅ Alice login succeeded")
            status, data, raw = _adopt("Snow")
            if status == 201:
                elfie_id_1 = data.get("elfie_id", "")
                print(f"    ✅ Adopted Snow (elfie_id={elfie_id_1})")

                status, data, raw = alice.get(
                    "/api/v1/elfies",
                    headers={"X-CSRF-Token": alice_csrf},
                )
                if status == 200 and isinstance(data, list) and len(data) >= 1:
                    names = [e["name"] for e in data]
                    if "Snow" in names:
                        print("    ✅ Snow appears in Alice's Elfie list")
                        results[1] = True
                    else:
                        print(f"    ❌ Elfie did not appear in the list: {names}")
                else:
                    print(f"    ❌ Failed to query Elfie list: {status} {raw[:200]}")
            else:
                print(f"    ❌ Adoption failed: {status} {raw[:200]}")
        else:
            print("    ❌ Alice login failed")

        # ==================================================================
        # Step 3: Verify the 3-Elfie adoption limit.
        # ==================================================================
        print("  [Step 3/5] Verify Alice's 3-Elfie adoption limit")

        s2, _, _ = _adopt("Sunny")
        if s2 != 201:
            print(f"    ❌ Second adoption failed ({s2}); skipping limit check")
        else:
            s3, _, _ = _adopt("Blue")
            if s3 != 201:
                print(f"    ❌ Third adoption failed ({s3}); skipping limit check")
            else:
                s4, _, _ = _adopt("Clover")
                if s4 == 409:
                    print("    ✅ Fourth adoption was rejected (409 limit is correct)")
                    results[2] = True
                else:
                    print(f"    ❌ Fourth adoption expected 409 but got {s4}")

        # ==================================================================
        # Step 4: Verify Elfies via HTTP.
        # ==================================================================
        print("  [Step 4/5] Verify Elfies exist (HTTP)")
        status, data, raw = alice.get(
            "/api/v1/elfies",
            headers={"X-CSRF-Token": alice_csrf},
        )
        if status == 200 and isinstance(data, list):
            count = len(data)
            print(f"    ✅ Alice has {count} Elfies")
            if count == 3:
                results[3] = True
                print("    ✅ The 3-Elfie limit is enforced")
            else:
                print(f"    ⚠️ Elfie count is {count}; expected 3")
        else:
            print(f"    ❌ Query failed: {status} {raw[:200]}")

        # ==================================================================
        # Step 5: Owner can view all Elfies.
        # ==================================================================
        print("  [Step 5/5] Owner views all Elfies")
        ok, owner_csrf2 = owner.login("owner", owner_password)
        if ok:
            status, data, raw = owner.get(
                "/api/owner/elfies",
                headers={"X-CSRF-Token": owner_csrf2},
            )
            if status == 200 and isinstance(data, list):
                names = [e["name"] for e in data]
                print(f"    ✅ Owner sees {len(data)} Elfies: {names}")
                if len(data) >= 3:
                    results[4] = True
                else:
                    print(f"    ⚠️ Owner sees only {len(data)}; expected at least 3")
            else:
                print(f"    ❌ Owner failed to query Elfies: {status} {raw[:200]}")
        else:
            print("    ❌ Owner re-login failed")

    except Exception as exc:
        print(f"\n  ❌ Test raised an exception: {exc}")
        import traceback

        traceback.print_exc()

    finally:
        print()
        print("  🧹 Cleaning up child process...")
        process.terminate()
        try:
            process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2.0)
        shutil.rmtree(data_home, ignore_errors=True)

    # Report
    print()
    print("=" * 60)
    print("  E2E verification report")
    print("=" * 60)

    labels = [
        "Step 1: Owner login -> create alice",
        "Step 2: Alice adoption -> Elfie appears",
        "Step 3: 3-Elfie limit -> 4th request returns 409",
        "Step 4: Elfies exist (HTTP verification)",
        "Step 5: Owner multi-tenant visibility",
    ]

    passed = sum(1 for r in results if r)
    for _i, (label, ok) in enumerate(zip(labels, results)):
        symbol = "✅" if ok else "❌"
        print(f"  {symbol} {label}")

    print("=" * 60)
    total = len(labels)
    if passed == total:
        print(f"  Result: {passed}/{total} passed — all checks passed!")
    else:
        print(f"  Result: {passed}/{total} passed — {total - passed} checks failed")
    print()

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
