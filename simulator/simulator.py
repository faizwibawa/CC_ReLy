"""ReLy traffic-signal simulator (runs on your own computer).

Generates SIMULATED phase changes and congestion for the signals in signals_seed.json and
sends them to the ReLy API. It uses only the Python standard library.

    python simulator/simulator.py               # run until Ctrl+C
    python simulator/simulator.py --once        # register + one update per signal, then exit
    python simulator/simulator.py --duration 300

Behaviour
- Startup: each seed signal is registered with POST /signals only if it does not exist yet
  (GET first), so restarting the simulator never creates duplicates.
- Updates are event-driven: a PUT is sent only when a light actually changes phase
  (GREEN -> YELLOW -> RED -> GREEN), with the full duration of the new phase as
  remaining_seconds. Congestion is re-rolled each time a light turns RED.
- Every PUT carries ?if_source=SIMULATOR. If an operator has switched a signal to MANUAL,
  the API answers 409 and the simulator leaves that signal alone until it is switched back.
- Network/API errors are logged and retried on the next phase change; the simulator keeps
  running.
"""
import argparse
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
NEXT_PHASE = {"GREEN": "YELLOW", "YELLOW": "RED", "RED": "GREEN"}


# --------------------------------------------------------------------------- config
def load_env():
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip())


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# --------------------------------------------------------------------------- HTTP
class ApiError(Exception):
    def __init__(self, status, body):
        super().__init__(f"HTTP {status}: {body}")
        self.status = status
        self.body = body


class Api:
    def __init__(self, base_url, timeout=10):
        self.base = base_url.rstrip("/")
        self.timeout = timeout

    def call(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(
            self.base + path, data=data, method=method,
            headers={"Content-Type": "application/json", "User-Agent": "ReLy-Simulator/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                raw = res.read().decode()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as err:
            raw = err.read().decode()
            try:
                parsed = json.loads(raw)
            except ValueError:
                parsed = raw
            raise ApiError(err.code, parsed) from None


# --------------------------------------------------------------------------- model
class SimSignal:
    def __init__(self, spec, rng):
        self.base = spec["signal"]
        self.id = self.base["signal_id"]
        self.cycle = spec["cycle"]
        self.weights = spec["congestion_weights"]
        self.rng = rng
        self.paused = False      # True while an operator has it on MANUAL
        self.retired = False     # True if the record was deleted by an operator
        # start at a random point in the cycle so lights are not synchronised
        self.phase = rng.choice(["GREEN", "YELLOW", "RED"])
        self.phase_end = time.time() + rng.uniform(1, self.cycle[self.phase])
        self.congestion = self._roll_congestion()

    def _roll_congestion(self):
        levels = list(self.weights)
        return self.rng.choices(levels, weights=[self.weights[l] for l in levels])[0]

    def confidence(self):
        return round(self.rng.uniform(0.85, 0.97), 2)

    def remaining(self):
        return max(0, int(round(self.phase_end - time.time())))

    def advance(self):
        self.phase = NEXT_PHASE[self.phase]
        self.phase_end = time.time() + self.cycle[self.phase]
        if self.phase == "RED":
            self.congestion = self._roll_congestion()

    def update_body(self):
        return {
            "current_phase": self.phase,
            "remaining_seconds": self.remaining(),
            "confidence_score": self.confidence(),
            "congestion_level": self.congestion,
        }

    def create_body(self):
        body = dict(self.base)
        body.update(self.update_body())
        body["data_source"] = "SIMULATOR"
        return body


# --------------------------------------------------------------------------- actions
def register(api, sim):
    """Create the record only if it does not exist yet (no duplicates)."""
    try:
        current = api.call("GET", f"/signals/{sim.id}")
        sim.paused = current.get("data_source") == "MANUAL"
        log(f"{sim.id}: already registered (source={current.get('data_source')})")
        return True
    except ApiError as err:
        if err.status != 404:
            raise
    api.call("POST", "/signals", sim.create_body())
    log(f"{sim.id}: registered")
    return True


def push(api, sim):
    try:
        api.call("PUT", f"/signals/{sim.id}?if_source=SIMULATOR", sim.update_body())
        if sim.paused:
            log(f"{sim.id}: back under SIMULATOR control")
        sim.paused = False
        flag = "  <-- RED + HEAVY" if sim.phase == "RED" and sim.congestion == "HEAVY" else ""
        log(f"{sim.id}: {sim.phase:<6} {sim.remaining():>3}s  congestion={sim.congestion}{flag}")
    except ApiError as err:
        if err.status == 409:
            if not sim.paused:
                log(f"{sim.id}: MANUAL override detected - skipping until switched back")
            sim.paused = True
        elif err.status == 404:
            log(f"{sim.id}: record was deleted by an operator - no longer simulated")
            sim.retired = True
        else:
            log(f"{sim.id}: API error {err}")
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        log(f"{sim.id}: network error ({err}); will retry on next phase change")


def resync(api, sims):
    """Periodically re-read sources so paused signals resume when set back to SIMULATOR."""
    try:
        items = {i["signal_id"]: i for i in api.call("GET", "/signals")["items"]}
    except (ApiError, urllib.error.URLError, TimeoutError, OSError) as err:
        log(f"resync failed ({err})")
        return
    for sim in sims:
        rec = items.get(sim.id)
        if rec is None:
            continue
        if sim.paused and rec.get("data_source") == "SIMULATOR":
            push(api, sim)


# --------------------------------------------------------------------------- main
def main():
    load_env()
    parser = argparse.ArgumentParser(description="ReLy traffic signal simulator (SIMULATED data)")
    parser.add_argument("--api-url", default=os.environ.get("RELY_API_URL"))
    parser.add_argument("--seed-file", default=os.environ.get(
        "RELY_SIM_SEED_FILE", os.path.join(ROOT, "simulator", "signals_seed.json")))
    parser.add_argument("--resync", type=int, default=int(os.environ.get("RELY_SIM_RESYNC_SECONDS", 60)))
    parser.add_argument("--duration", type=int, default=0, help="stop after N seconds (0 = forever)")
    parser.add_argument("--once", action="store_true", help="register + one update each, then exit")
    parser.add_argument("--random-seed", type=int, default=None)
    args = parser.parse_args()

    if not args.api_url:
        sys.exit("RELY_API_URL is not set. Copy .env.example to .env and fill it in.")
    seed_path = args.seed_file if os.path.isabs(args.seed_file) else os.path.join(ROOT, args.seed_file)
    with open(seed_path, encoding="utf-8") as fh:
        seed = json.load(fh)

    rng = random.Random(args.random_seed)
    api = Api(args.api_url)
    sims = [SimSignal(spec, rng) for spec in seed["signals"]]

    log(f"ReLy simulator starting with {len(sims)} SIMULATED signals")
    for sim in sims:
        for attempt in range(3):
            try:
                register(api, sim)
                break
            except (ApiError, urllib.error.URLError, TimeoutError, OSError) as err:
                log(f"{sim.id}: registration failed ({err}), attempt {attempt + 1}/3")
                time.sleep(2 * (attempt + 1))
        else:
            sys.exit("Could not reach the ReLy API. Check RELY_API_URL and that the stack is deployed.")

    for sim in sims:
        if not sim.paused:
            push(api, sim)
    if args.once:
        log("--once: done")
        return

    started = time.time()
    last_resync = time.time()
    try:
        while True:
            now = time.time()
            if args.duration and now - started >= args.duration:
                log("duration reached, stopping")
                break
            for sim in sims:
                if sim.retired:
                    continue
                if now >= sim.phase_end:
                    sim.advance()
                    if not sim.paused:
                        push(api, sim)
            if now - last_resync >= args.resync:
                resync(api, sims)
                last_resync = now
            active = [s.phase_end for s in sims if not s.retired]
            if not active:
                log("no signals left to simulate, stopping")
                break
            time.sleep(max(0.2, min(1.0, min(active) - time.time())))
    except KeyboardInterrupt:
        log("stopped by user (Ctrl+C)")


if __name__ == "__main__":
    main()
