import os
import random
import time

import requests

APP_URL = os.getenv("LOADGEN_APP_URL", "http://app:8000")
PROFILE = os.getenv("LOADGEN_PROFILE", "steady").strip().lower()
RPS = float(os.getenv("LOADGEN_RPS", "5.0"))
WORK_MS = int(os.getenv("LOADGEN_WORK_MS", "20"))
JITTER = float(os.getenv("LOADGEN_JITTER", "0.1"))
TIMEOUT_S = float(os.getenv("LOADGEN_TIMEOUT_S", "1.5"))
PATHS = [p.strip() for p in os.getenv("LOADGEN_PATHS", "/work").split(",") if p.strip()]
SEED = int(os.getenv("LOADGEN_SEED", "42"))
RNG = random.Random(SEED)


def pick_path() -> str:
    if PROFILE == "mixed":
        choices = ["/work", "/health", "/dns/test?name=example.com", "/db/slow?seconds=1"]
        return RNG.choice(choices)
    if PROFILE == "bursty":
        return "/work"
    return RNG.choice(PATHS) if PATHS else "/work"


def calc_sleep(base: float) -> float:
    if PROFILE == "bursty":
        if RNG.random() < 0.2:
            return max(0.001, base * 0.25)
        return max(0.001, base * 2.0)
    jitter = 1.0 + RNG.uniform(-JITTER, JITTER)
    return max(0.001, base * jitter)


def main() -> None:
    session = requests.Session()
    base_interval = 1.0 / max(0.1, RPS)
    while True:
        t0 = time.time()
        path = pick_path()
        url = f"{APP_URL}{path}"
        try:
            if path.startswith("/work"):
                session.get(url, params={"ms": WORK_MS}, timeout=TIMEOUT_S)
            else:
                session.get(url, timeout=TIMEOUT_S)
        except Exception:
            pass
        elapsed = time.time() - t0
        time.sleep(max(0.001, calc_sleep(base_interval) - elapsed))


if __name__ == "__main__":
    main()
