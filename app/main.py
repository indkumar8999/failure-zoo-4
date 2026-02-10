import os
import time
import threading
from typing import Optional, Dict, Any

import dns.resolver
import requests
from fastapi import FastAPI, HTTPException
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool

APP_NAME = "failure-zoo-app"

DATABASE_URL = os.getenv("DATABASE_URL")
DOWNSTREAM_URL = os.getenv("DOWNSTREAM_URL", "http://downstream:9000")
MAX_DB_INFLIGHT = int(os.getenv("MAX_DB_INFLIGHT", "10"))

CHAOS_MEM_LIMIT_MB = int(os.getenv("CHAOS_MEM_LIMIT_MB", "800"))
CHAOS_FD_LIMIT = int(os.getenv("CHAOS_FD_LIMIT", "5000"))

DATA_DIR = "/data"
EVENTS_FILE = os.path.join(DATA_DIR, "events", "chaos_events.jsonl")

REQS = Counter("http_requests_total", "Requests", ["path", "code"])
LAT = Histogram("http_request_latency_seconds", "Latency", ["path"])
CHAOS = Gauge("chaos_mode", "Chaos modes enabled", ["mode"])
LEAK_MB = Gauge("leak_mb", "Approx leaked memory in MB")
OPEN_FDS = Gauge("open_fds_simulated", "FDs held open by simulator")
DISK_FILL_MB = Gauge("disk_fill_mb", "MB filled in /data by simulator")
DB_INFLIGHT = Gauge("db_inflight", "DB operations in-flight (app gate)")
RETRY_CALLS = Counter("retry_calls_total", "Downstream calls attempted", ["endpoint", "result"])

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

app = FastAPI(title=APP_NAME)

state_lock = threading.Lock()

cpu_threads: list[threading.Thread] = []
cpu_stop = threading.Event()

lock_convoy_stop = threading.Event()
lock_convoy_threads: list[threading.Thread] = []
convoy_lock = threading.Lock()

mem_leak: list[bytearray] = []
mem_leak_stop = threading.Event()

fd_leak_files: list[object] = []
fd_leak_stop = threading.Event()

retry_storm_stop = threading.Event()
retry_thread: Optional[threading.Thread] = None

db_gate = threading.BoundedSemaphore(MAX_DB_INFLIGHT)

dns_server: Optional[str] = None


def _now_epoch() -> float:
    return time.time()


def _write_event(event: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(EVENTS_FILE), exist_ok=True)
        event.setdefault("ts", _now_epoch())
        import json
        with open(EVENTS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, separators=(",", ":")) + "\n")
    except Exception:
        pass


def _set_chaos_metric(mode: str, enabled: bool, extra: Optional[Dict[str, Any]] = None) -> None:
    CHAOS.labels(mode).set(1 if enabled else 0)
    ev = {"type": "chaos", "mode": mode, "enabled": enabled}
    if extra:
        ev.update(extra)
    _write_event(ev)




def instrument(path: str):
    """Decorator to record request count + latency for a FastAPI handler."""
    def deco(func):
        def wrapper(*args, **kwargs):
            t0 = time.time()
            try:
                resp = func(*args, **kwargs)
                REQS.labels(path=path, code="200").inc()
                return resp
            except HTTPException as e:
                REQS.labels(path=path, code=str(e.status_code)).inc()
                raise
            finally:
                LAT.labels(path=path).observe(time.time() - t0)
        return wrapper
    return deco

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
@instrument("/health")
def health():
    return {"ok": True}


@app.get("/work")
def work(ms: int = 20):
    t0 = time.time()
    x = 0
    for i in range(3000):
        x ^= (i * 2654435761) & 0xFFFFFFFF
    dt = time.time() - t0
    if ms > 0:
        time.sleep(ms / 1000.0)
    return {"ok": True, "cpu_dt_ms": int(dt * 1000), "x": x}


# CPU saturation
def _cpu_burner():
    while not cpu_stop.is_set():
        x = 0
        for i in range(500000):
            x ^= i
        if x == 42:
            time.sleep(0)


@app.post("/chaos/cpu/start")
def chaos_cpu_start(workers: int = 2):
    with state_lock:
        if cpu_threads:
            return {"started": True, "workers": len(cpu_threads)}
        cpu_stop.clear()
        for _ in range(max(1, min(workers, 64))):
            t = threading.Thread(target=_cpu_burner, daemon=True)
            cpu_threads.append(t)
            t.start()
        _set_chaos_metric("cpu", True, {"workers": len(cpu_threads)})
    return {"started": True, "workers": len(cpu_threads)}


@app.post("/chaos/cpu/stop")
def chaos_cpu_stop():
    with state_lock:
        cpu_stop.set()
        cpu_threads.clear()
        _set_chaos_metric("cpu", False)
    return {"stopped": True}


# Lock convoy
def _lock_convoy():
    while not lock_convoy_stop.is_set():
        with convoy_lock:
            pass


@app.post("/chaos/lock_convoy/start")
def chaos_lock_convoy_start(threads: int = 50):
    with state_lock:
        if lock_convoy_threads:
            return {"started": True, "threads": len(lock_convoy_threads)}
        lock_convoy_stop.clear()
        for _ in range(max(2, min(threads, 500))):
            t = threading.Thread(target=_lock_convoy, daemon=True)
            lock_convoy_threads.append(t)
            t.start()
        _set_chaos_metric("lock_convoy", True, {"threads": len(lock_convoy_threads)})
    return {"started": True, "threads": len(lock_convoy_threads)}


@app.post("/chaos/lock_convoy/stop")
def chaos_lock_convoy_stop():
    with state_lock:
        lock_convoy_stop.set()
        lock_convoy_threads.clear()
        _set_chaos_metric("lock_convoy", False)
    return {"stopped": True}


# Memory leak
@app.post("/chaos/mem/leak/start")
def chaos_mem_leak_start(mb_per_sec: int = 20):
    if mb_per_sec <= 0:
        raise HTTPException(400, "mb_per_sec must be > 0")
    mem_leak_stop.clear()
    _set_chaos_metric("mem_leak", True, {"mb_per_sec": mb_per_sec, "cap_mb": CHAOS_MEM_LIMIT_MB})

    def run():
        while not mem_leak_stop.is_set():
            with state_lock:
                cur_mb = sum(len(b) for b in mem_leak) // (1024 * 1024)
                if cur_mb >= CHAOS_MEM_LIMIT_MB:
                    LEAK_MB.set(cur_mb)
                    time.sleep(1)
                    continue
                b = bytearray(mb_per_sec * 1024 * 1024)
                for j in range(0, len(b), 4096):
                    b[j] = 1
                mem_leak.append(b)
                cur_mb = sum(len(x) for x in mem_leak) // (1024 * 1024)
                LEAK_MB.set(cur_mb)
            time.sleep(1)

    threading.Thread(target=run, daemon=True).start()
    return {"started": True, "mb_per_sec": mb_per_sec, "cap_mb": CHAOS_MEM_LIMIT_MB}


@app.post("/chaos/mem/leak/stop")
def chaos_mem_leak_stop():
    mem_leak_stop.set()
    with state_lock:
        mem_leak.clear()
        LEAK_MB.set(0)
        _set_chaos_metric("mem_leak", False)
    return {"stopped": True}


@app.post("/chaos/mem/pressure")
def chaos_mem_pressure(mb: int = 300):
    mb = max(1, min(mb, CHAOS_MEM_LIMIT_MB))
    _write_event({"type": "chaos", "mode": "mem_pressure", "enabled": True, "mb": mb, "duration_s": 30})
    b = bytearray(mb * 1024 * 1024)
    for i in range(0, len(b), 4096):
        b[i] = 1
    time.sleep(30)
    _write_event({"type": "chaos", "mode": "mem_pressure", "enabled": False})
    return {"held_mb": mb, "duration_s": 30}


# FD leak
@app.post("/chaos/fd/leak/start")
def chaos_fd_leak_start(rate_per_sec: int = 100):
    if rate_per_sec <= 0:
        raise HTTPException(400, "rate_per_sec must be > 0")
    fd_leak_stop.clear()
    _set_chaos_metric("fd_leak", True, {"rate_per_sec": rate_per_sec, "cap": CHAOS_FD_LIMIT})

    def run():
        while not fd_leak_stop.is_set():
            with state_lock:
                if len(fd_leak_files) >= CHAOS_FD_LIMIT:
                    OPEN_FDS.set(len(fd_leak_files))
                    time.sleep(1)
                    continue
                for _ in range(rate_per_sec):
                    if len(fd_leak_files) >= CHAOS_FD_LIMIT:
                        break
                    f = open("/data/fd_leak.tmp", "a", buffering=1)
                    f.write("x")
                    fd_leak_files.append(f)
                OPEN_FDS.set(len(fd_leak_files))
            time.sleep(1)

    threading.Thread(target=run, daemon=True).start()
    return {"started": True, "rate_per_sec": rate_per_sec, "cap": CHAOS_FD_LIMIT}


@app.post("/chaos/fd/leak/stop")
def chaos_fd_leak_stop():
    fd_leak_stop.set()
    with state_lock:
        for f in fd_leak_files:
            try:
                f.close()
            except Exception:
                pass
        fd_leak_files.clear()
        OPEN_FDS.set(0)
        _set_chaos_metric("fd_leak", False)
    return {"stopped": True}


# Disk fill / fsync storm
@app.post("/chaos/disk/fill")
def chaos_disk_fill(mb: int = 200, fsync_each_mb: bool = False):
    mb = max(1, min(mb, 50000))
    path = "/data/fill.bin"
    with open(path, "ab") as f:
        for _ in range(mb):
            f.write(b"\0" * (1024 * 1024))
            if fsync_each_mb:
                os.fsync(f.fileno())
    DISK_FILL_MB.set(int(os.path.getsize(path) / (1024 * 1024)))
    _set_chaos_metric("disk_fill", True, {"filled_mb_total": int(DISK_FILL_MB._value.get())})
    if fsync_each_mb:
        _set_chaos_metric("fsync_storm", True, {"fsync_each_mb": True})
    return {"filled_mb_total": int(DISK_FILL_MB._value.get()), "fsync_each_mb": fsync_each_mb}


@app.post("/chaos/disk/clear")
def chaos_disk_clear():
    path = "/data/fill.bin"
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception as e:
        raise HTTPException(500, f"failed to remove: {e}")
    DISK_FILL_MB.set(0)
    _set_chaos_metric("disk_fill", False)
    _set_chaos_metric("fsync_storm", False)
    return {"cleared": True}


# DB slow query + inflight gate
@app.get("/db/slow")
def db_slow(seconds: int = 2):
    seconds = max(0, min(seconds, 60))
    with db_gate:
        DB_INFLIGHT.set(MAX_DB_INFLIGHT - db_gate._value)
        with engine.begin() as conn:
            conn.execute(text("SELECT pg_sleep(:s)"), {"s": seconds})
    DB_INFLIGHT.set(MAX_DB_INFLIGHT - db_gate._value)
    return {"ok": True, "slept_s": seconds}


@app.post("/chaos/db_gate/set")
def set_db_gate(max_inflight: int = 2):
    global db_gate, MAX_DB_INFLIGHT
    max_inflight = max(1, min(max_inflight, 200))
    with state_lock:
        MAX_DB_INFLIGHT = max_inflight
        db_gate = threading.BoundedSemaphore(MAX_DB_INFLIGHT)
    _write_event({"type": "chaos", "mode": "db_gate", "enabled": True, "max_inflight": MAX_DB_INFLIGHT})
    return {"max_db_inflight": MAX_DB_INFLIGHT}


# Retry storm
def _retry_storm(qps: int, endpoint: str, retries: int, timeout_s: float):
    session = requests.Session()
    url = f"{DOWNSTREAM_URL}{endpoint}"
    interval = 1.0 / max(1, qps)
    while not retry_storm_stop.is_set():
        t0 = time.time()
        ok = False
        for _ in range(retries + 1):
            try:
                RETRY_CALLS.labels(endpoint=endpoint, result="attempt").inc()
                r = session.get(url, timeout=timeout_s)
                if r.status_code == 200:
                    ok = True
                    RETRY_CALLS.labels(endpoint=endpoint, result="ok").inc()
                    break
                RETRY_CALLS.labels(endpoint=endpoint, result="non_200").inc()
            except Exception:
                RETRY_CALLS.labels(endpoint=endpoint, result="exception").inc()
        if not ok:
            RETRY_CALLS.labels(endpoint=endpoint, result="failed").inc()
        dt = time.time() - t0
        time.sleep(max(0.0, interval - dt))


@app.post("/chaos/retry_storm/start")
def retry_storm_start(qps: int = 20, endpoint: str = "/flaky", retries: int = 3, timeout_s: float = 0.2):
    global retry_thread
    with state_lock:
        if retry_thread and retry_thread.is_alive():
            return {"started": True}
        retry_storm_stop.clear()
        retry_thread = threading.Thread(target=_retry_storm, args=(qps, endpoint, retries, timeout_s), daemon=True)
        retry_thread.start()
        _set_chaos_metric("retry_storm", True, {"qps": qps, "endpoint": endpoint, "retries": retries})
    return {"started": True, "qps": qps, "endpoint": endpoint, "retries": retries}


@app.post("/chaos/retry_storm/stop")
def retry_storm_stop_fn():
    retry_storm_stop.set()
    _set_chaos_metric("retry_storm", False)
    return {"stopped": True}


# DNS failures (controlled lookup)
@app.post("/chaos/dns/set_server")
def dns_set_server(server: Optional[str] = None):
    global dns_server
    dns_server = server if server else None
    _set_chaos_metric("dns_test", True if dns_server else False, {"dns_server": dns_server})
    return {"dns_server": dns_server}


@app.get("/dns/test")
def dns_test(name: str = "example.com"):
    resolver = dns.resolver.Resolver(configure=True)
    if dns_server:
        resolver.nameservers = [dns_server]
        resolver.timeout = 0.5
        resolver.lifetime = 0.8
    try:
        ans = resolver.resolve(name, "A")
        ips = [r.address for r in ans]
        return {"ok": True, "name": name, "ips": ips, "dns_server": dns_server}
    except Exception as e:
        raise HTTPException(502, f"DNS lookup failed: {e}")


@app.post("/chaos/reset")
def chaos_reset():
    chaos_cpu_stop()
    chaos_lock_convoy_stop()
    chaos_mem_leak_stop()
    chaos_fd_leak_stop()
    retry_storm_stop_fn()
    chaos_disk_clear()
    dns_set_server(None)
    set_db_gate(10)
    _write_event({"type": "chaos", "mode": "reset", "enabled": True})
    return {"reset": True}
