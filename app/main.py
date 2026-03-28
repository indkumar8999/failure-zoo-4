import os
import time
import threading
from typing import Optional, Dict, Any

import dns.resolver
import requests
import numpy as np
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

# Normal behavior control flags
normal_behavior_stop = threading.Event()


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


# ============================================================================
# Normal Application Behavior: Background workers to simulate real workload
# ============================================================================

def _normal_behavior_matrix_computation():
    """
    Simulates CPU-intensive work: 100x100 random matrix multiplication every 5 seconds.
    This is normal application load that tests should not interfere with.
    """
    import random
    import numpy as np
    
    while not normal_behavior_stop.is_set():
        try:
            # Create two 100x100 random matrices
            size = 100
            matrix_a = np.random.rand(size, size)
            matrix_b = np.random.rand(size, size)
            
            # Perform matrix multiplication (CPU-intensive)
            result = np.dot(matrix_a, matrix_b)
            
            # Calculate mean to verify computation happened
            mean_val = np.mean(result)
            
            _write_event({
                "type": "normal_behavior",
                "operation": "matrix_multiplication",
                "size": size,
                "result_mean": float(mean_val)
            })
            
            # Wait 5 seconds before next computation
            time.sleep(5)
        except Exception as e:
            _write_event({"type": "normal_behavior", "operation": "matrix_computation_error", "error": str(e)})
            time.sleep(5)


def _normal_behavior_file_operations():
    """
    Simulates file I/O: creates, writes, reads, and deletes files in /data/normal_files.
    This is normal file system activity that should be measurable.
    """
    import random
    import string
    
    work_dir = "/data/normal_files"
    os.makedirs(work_dir, exist_ok=True)
    
    while not normal_behavior_stop.is_set():
        try:
            # Random file operations cycle
            operation = random.choice(["create", "read", "delete"])
            
            if operation == "create":
                # Create a file with random content
                filename = os.path.join(work_dir, f"file_{int(time.time() * 1000000) % 10000}.txt")
                content = "".join(random.choices(string.ascii_letters + string.digits, k=1000))
                with open(filename, "w") as f:
                    f.write(content)
                _write_event({"type": "normal_behavior", "operation": "file_create", "path": filename})
            
            elif operation == "read":
                # Read a random existing file
                files = os.listdir(work_dir)
                if files:
                    filepath = os.path.join(work_dir, random.choice(files))
                    try:
                        with open(filepath, "r") as f:
                            content = f.read()
                        _write_event({"type": "normal_behavior", "operation": "file_read", "path": filepath, "size": len(content)})
                    except Exception:
                        pass
            
            elif operation == "delete":
                # Delete a random file
                files = os.listdir(work_dir)
                if files:
                    filepath = os.path.join(work_dir, random.choice(files))
                    try:
                        os.remove(filepath)
                        _write_event({"type": "normal_behavior", "operation": "file_delete", "path": filepath})
                    except Exception:
                        pass
            
            # Sleep for 2 seconds before next operation
            time.sleep(2)
            
            # Cleanup: remove old files to prevent accumulation
            try:
                files = os.listdir(work_dir)
                if len(files) > 50:  # Keep max 50 files
                    for f in sorted(files)[:-20]:
                        try:
                            os.remove(os.path.join(work_dir, f))
                        except Exception:
                            pass
            except Exception:
                pass
                
        except Exception as e:
            _write_event({"type": "normal_behavior", "operation": "file_operations_error", "error": str(e)})
            time.sleep(2)


def _normal_behavior_web_requests():
    """
    Simulates external API calls: periodically fetches data from /work endpoint
    and tracks response time. This simulates a service making HTTP requests.
    """
    session = requests.Session()
    
    while not normal_behavior_stop.is_set():
        try:
            # Make request to internal /work endpoint (simulates downstream API call)
            start_time = time.time()
            try:
                response = session.get("http://localhost:8000/work", timeout=5)
                elapsed_ms = (time.time() - start_time) * 1000
                
                _write_event({
                    "type": "normal_behavior",
                    "operation": "web_request",
                    "endpoint": "/work",
                    "status_code": response.status_code,
                    "response_time_ms": elapsed_ms,
                    "success": response.status_code == 200
                })
            except requests.Timeout:
                elapsed_ms = (time.time() - start_time) * 1000
                _write_event({
                    "type": "normal_behavior",
                    "operation": "web_request",
                    "endpoint": "/work",
                    "error": "timeout",
                    "response_time_ms": elapsed_ms
                })
            except Exception as e:
                elapsed_ms = (time.time() - start_time) * 1000
                _write_event({
                    "type": "normal_behavior",
                    "operation": "web_request",
                    "endpoint": "/work",
                    "error": str(e),
                    "response_time_ms": elapsed_ms
                })
            
            # Wait 3 seconds before next request
            time.sleep(3)
            
        except Exception as e:
            _write_event({"type": "normal_behavior", "operation": "web_request_error", "error": str(e)})
            time.sleep(3)


def _start_normal_behavior():
    """Start all normal behavior background threads on application startup."""
    normal_behavior_stop.clear()
    
    # Start matrix computation worker
    threading.Thread(
        target=_normal_behavior_matrix_computation,
        name="normal-matrix-worker",
        daemon=True
    ).start()
    
    # Start file operations worker
    threading.Thread(
        target=_normal_behavior_file_operations,
        name="normal-files-worker",
        daemon=True
    ).start()
    
    # Start web request worker
    threading.Thread(
        target=_normal_behavior_web_requests,
        name="normal-requests-worker",
        daemon=True
    ).start()
    
    _write_event({"type": "startup", "event": "normal_behavior_started"})


def instrument(path: str):
    """Decorator to record request count + latency for a FastAPI handler."""
    from functools import wraps
    def deco(func):
        @wraps(func)
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


# Network chaos (via ToxiProxy)
TOXI_URL = os.getenv("TOXI_URL", "http://toxiproxy:8474")


def _toxi_request(method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Make request to ToxiProxy API."""
    url = f"{TOXI_URL}{path}"
    try:
        r = requests.request(method, url, json=payload, timeout=5)
        r.raise_for_status()
        if r.headers.get("content-type", "").startswith("application/json"):
            return r.json()
        return None
    except Exception as e:
        raise HTTPException(503, f"ToxiProxy error: {e}")


def _ensure_proxy():
    """Ensure the downstream proxy exists in ToxiProxy."""
    try:
        proxies = _toxi_request("GET", "/proxies") or {}
        if "downstream" not in proxies:
            _toxi_request("POST", "/proxies", {
                "name": "downstream",
                "listen": "0.0.0.0:8666",
                "upstream": "downstream:9000"
            })
    except Exception:
        pass  # Proxy may already exist


def _add_toxic(name: str, toxic_type: str, attributes: Dict[str, Any], toxicity: float = 1.0):
    """Add a toxic to the downstream proxy."""
    _ensure_proxy()
    _toxi_request("POST", "/proxies/downstream/toxics", {
        "name": name,
        "type": toxic_type,
        "stream": "downstream",
        "toxicity": toxicity,
        "attributes": attributes,
    })
    _write_event({"type": "chaos", "mode": f"net_{toxic_type}", "enabled": True, "toxic": name, "attributes": attributes})


def _clear_toxics():
    """Clear all toxics from the downstream proxy."""
    try:
        _ensure_proxy()
        # Get existing toxics
        proxies = _toxi_request("GET", "/proxies") or {}
        downstream = proxies.get("downstream", {})
        toxics = downstream.get("toxics", [])
        
        # Delete each toxic individually
        for toxic in toxics:
            toxic_name = toxic.get("name", "")
            if toxic_name:
                try:
                    _toxi_request("DELETE", f"/proxies/downstream/toxics/{toxic_name}")
                except Exception:
                    pass  # Ignore errors deleting individual toxics
        
        _write_event({"type": "chaos", "mode": "net_clear", "enabled": True})
    except Exception as e:
        raise HTTPException(503, f"Failed to clear toxics: {e}")


@app.post("/chaos/net/latency")
def chaos_net_latency(ms: int = 200):
    """Add network latency to downstream connections."""
    ms = max(0, min(ms, 10000))  # 0-10000 ms
    _clear_toxics()
    jitter = int(ms * 0.2)  # 20% jitter
    _add_toxic("latency", "latency", {"latency": ms, "jitter": jitter})
    return {"latency_ms": ms, "jitter_ms": jitter}


@app.post("/chaos/net/bandwidth")
def chaos_net_bandwidth(kbps: int = 64):
    """Limit bandwidth to downstream connections."""
    kbps = max(1, min(kbps, 100000))  # 1-100000 kbps
    _clear_toxics()
    _add_toxic("bandwidth", "bandwidth", {"rate": kbps})
    return {"bandwidth_kbps": kbps}


@app.post("/chaos/net/reset_peer")
def chaos_net_reset_peer():
    """Reset peer connections (close connections randomly)."""
    _clear_toxics()
    _add_toxic("reset", "reset_peer", {})
    return {"reset_peer": True}


@app.post("/chaos/net/clear")
def chaos_net_clear():
    """Clear all network toxics."""
    _clear_toxics()
    CHAOS.labels(mode="net_latency").set(0)
    CHAOS.labels(mode="net_bandwidth").set(0)
    CHAOS.labels(mode="net_reset_peer").set(0)
    return {"cleared": True}


@app.get("/chaos/net/status")
def chaos_net_status():
    """Get current network toxics status."""
    try:
        proxies = _toxi_request("GET", "/proxies") or {}
        downstream = proxies.get("downstream", {})
        toxics = downstream.get("toxics", [])
        return {
            "proxy_exists": "downstream" in proxies,
            "toxics": toxics,
            "count": len(toxics)
        }
    except Exception as e:
        raise HTTPException(503, f"Failed to get status: {e}")


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


# ============================================================================
# Application Startup: Initialize normal behavior workers
# ============================================================================

@app.on_event("startup")
def startup_event():
    """Called when the FastAPI application starts."""
    _start_normal_behavior()

