"""End-to-end smoke test against the DEPLOYED ReLy API (no third-party packages).

Usage (from repository root, with RELY_API_URL set in .env or the environment):
    python backend/tests/api_smoke_test.py

It creates a temporary signal, exercises every CRUD route plus error cases, deletes the
temporary signal again, and prints a PASS/FAIL table. Exit code 0 means all checks passed.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def load_env():
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip())


def request(base, method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        base + path, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            raw = res.read().decode()
            return res.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as err:
        raw = err.read().decode()
        return err.code, json.loads(raw) if raw else None


def main():
    load_env()
    base = os.environ.get("RELY_API_URL", "").rstrip("/")
    if not base:
        sys.exit("RELY_API_URL is not set (see .env.example)")

    try:
        request(base, "GET", "/")
    except urllib.error.URLError as err:
        sys.exit(f"Cannot reach {base}: {err.reason}. Is the stack deployed / server running?")

    sid = f"SMOKE-{int(time.time())}"
    signal = {
        "signal_id": sid,
        "location": "Smoke test junction (SIMULATED)",
        "latitude": -7.7956,
        "longitude": 110.3695,
        "current_phase": "RED",
        "remaining_seconds": 40,
        "confidence_score": 0.8,
        "congestion_level": "HEAVY",
        "detour": {"label": "Smoke-test detour", "lat": -7.79, "lng": 110.36},
        "data_source": "MANUAL",
    }

    checks = []

    def check(name, status, expected, extra_ok=True):
        ok = status == expected and extra_ok
        checks.append((name, expected, status, ok))

    s, b = request(base, "GET", "/")
    check("Health check            GET /", s, 200)

    s, b = request(base, "POST", "/signals", signal)
    check("Create                  POST /signals", s, 201, bool(b) and b.get("signal_id") == sid)

    s, b = request(base, "POST", "/signals", signal)
    check("Duplicate create -> 409 POST /signals", s, 409)

    s, b = request(base, "GET", "/signals")
    check("List                    GET /signals", s, 200,
          bool(b) and any(i["signal_id"] == sid for i in b.get("items", [])))

    s, b = request(base, "GET", f"/signals/{sid}")
    check("Read one                GET /signals/{id}", s, 200,
          bool(b) and 0 <= b.get("remaining_seconds", -1) <= 40)

    s, b = request(base, "PUT", f"/signals/{sid}", {"current_phase": "GREEN", "remaining_seconds": 25})
    check("Update                  PUT /signals/{id}", s, 200, bool(b) and b.get("current_phase") == "GREEN")

    s, b = request(base, "PUT", f"/signals/{sid}?if_source=SIMULATOR", {"current_phase": "RED"})
    check("Simulator blocked on MANUAL -> 409", s, 409)

    s, b = request(base, "POST", "/signals", dict(signal, signal_id=sid + "-BAD",
                                                 current_phase="BLUE", confidence_score=2))
    check("Invalid payload -> 400  POST /signals", s, 400)

    s, b = request(base, "GET", "/signals/DOES-NOT-EXIST")
    check("Missing record -> 404   GET /signals/{id}", s, 404)

    s, b = request(base, "DELETE", f"/signals/{sid}")
    check("Delete                  DELETE /signals/{id}", s, 200)

    s, b = request(base, "GET", f"/signals/{sid}")
    check("Deleted is gone -> 404  GET /signals/{id}", s, 404)

    print(f"ReLy API smoke test  ({time.strftime('%Y-%m-%d %H:%M:%S %Z')})")
    print(f"{'check':<44}{'expected':>9}{'actual':>8}  result")
    for name, expected, actual, ok in checks:
        print(f"{name:<44}{expected:>9}{actual:>8}  {'PASS' if ok else 'FAIL'}")
    passed = sum(1 for c in checks if c[3])
    print(f"\n{passed}/{len(checks)} checks passed")
    sys.exit(0 if passed == len(checks) else 1)


if __name__ == "__main__":
    main()
