import os
import sys
import time
import requests

APP = os.getenv("APP_BASE", "http://localhost:8000")
TOXI = os.getenv("TOXI_BASE", "http://localhost:8474")


def _cli_int(argv: list, idx: int, default: int) -> int:
    """Parse argv[idx] as int; accepts '20' and '20.0' from YAML float rendering."""
    if len(argv) <= idx:
        return default
    return int(float(argv[idx]))


def app_post(path, params=None, retries=8, backoff_s=1.0, timeout_s=5):
    last_exc = None
    for i in range(retries):
        try:
            r = requests.post(f"{APP}{path}", params=params, timeout=timeout_s)
            print(r.status_code, r.text)
            r.raise_for_status()
            return
        except Exception as exc:
            last_exc = exc
            if i == retries - 1:
                raise
            time.sleep(backoff_s)
    if last_exc:
        raise last_exc


def mark(mode, enabled, intensity=None):
    params = {"mode": mode, "enabled": str(bool(enabled)).lower()}
    if intensity is not None:
        params["intensity"] = intensity
    try:
        app_post("/chaos/mark", params=params, retries=3, backoff_s=0.5)
    except Exception as exc:
        # Best-effort marker so orchestration doesn't fail during startup races.
        print(f"WARN: failed to mark mode={mode} enabled={enabled}: {exc}")

def toxi(method, path, payload=None):
    url = f"{TOXI}{path}"
    r = requests.request(method, url, json=payload, timeout=5)
    if r.text:
        print(r.status_code, r.text)
    else:
        print(r.status_code)
    r.raise_for_status()
    if r.headers.get("content-type", "").startswith("application/json"):
        return r.json()
    return None

def ensure_proxy():
    proxies = toxi("GET", "/proxies") or {}
    if "downstream" in proxies:
        return
    toxi("POST", "/proxies", {"name":"downstream","listen":"0.0.0.0:8666","upstream":"downstream:9000"})

def clear_toxics():
    ensure_proxy()
    proxy = toxi("GET", "/proxies/downstream") or {}
    toxics = proxy.get("toxics", []) if isinstance(proxy, dict) else []
    for toxic in toxics:
        name = toxic.get("name")
        if name:
            toxi("DELETE", f"/proxies/downstream/toxics/{name}")
    mark("net_latency", False)
    mark("net_reset_peer", False)
    mark("net_bandwidth", False)

def add_toxic(name, toxic_type, attributes, toxicity=1.0, stream="downstream"):
    ensure_proxy()
    toxi("POST", "/proxies/downstream/toxics", {
        "name": name,
        "type": toxic_type,
        "stream": stream,
        "toxicity": toxicity,
        "attributes": attributes,
    })

def usage():
    print('Usage:\n  docker compose run --rm chaos reset\n  docker compose run --rm chaos cpu on [workers]\n  docker compose run --rm chaos cpu off\n  docker compose run --rm chaos lock on [threads]\n  docker compose run --rm chaos lock off\n  docker compose run --rm chaos memleak on [mb_per_sec]\n  docker compose run --rm chaos memleak off\n  docker compose run --rm chaos fdleak on [rate_per_sec]\n  docker compose run --rm chaos fdleak off\n  docker compose run --rm chaos disk fill [mb] [--fsync]\n  docker compose run --rm chaos disk clear\n  docker compose run --rm chaos dbgate [max_inflight]\n  docker compose run --rm chaos retrystorm on [qps]\n  docker compose run --rm chaos retrystorm off\n  docker compose run --rm chaos net latency [ms]\n  docker compose run --rm chaos net reset_peer\n  docker compose run --rm chaos net bandwidth [kbps]\n  docker compose run --rm chaos net clear\n  docker compose run --rm chaos dns bad\n  docker compose run --rm chaos dns ok\n')

def main():
    if len(sys.argv) < 2:
        usage()
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "reset":
        clear_toxics()
        app_post("/chaos/reset")
        return

    if cmd == "cpu":
        if sys.argv[2] == "on":
            workers = _cli_int(sys.argv, 3, 2)
            app_post("/chaos/cpu/start", {"workers": workers})
            return
        if sys.argv[2] == "off":
            app_post("/chaos/cpu/stop")
            return

    if cmd == "lock":
        if sys.argv[2] == "on":
            threads = _cli_int(sys.argv, 3, 80)
            app_post("/chaos/lock_convoy/start", {"threads": threads}, timeout_s=30)
            return
        if sys.argv[2] == "off":
            app_post("/chaos/lock_convoy/stop")
            return

    if cmd == "memleak":
        if sys.argv[2] == "on":
            rate = _cli_int(sys.argv, 3, 20)
            app_post("/chaos/mem/leak/start", {"mb_per_sec": rate})
            return
        if sys.argv[2] == "off":
            app_post("/chaos/mem/leak/stop")
            return

    if cmd == "fdleak":
        if sys.argv[2] == "on":
            rate = _cli_int(sys.argv, 3, 200)
            app_post("/chaos/fd/leak/start", {"rate_per_sec": rate})
            return
        if sys.argv[2] == "off":
            app_post("/chaos/fd/leak/stop")
            return

    if cmd == "disk":
        if sys.argv[2] == "fill":
            mb = _cli_int(sys.argv, 3, 200)
            fsync = "--fsync" in sys.argv
            app_post("/chaos/disk/fill", {"mb": mb, "fsync_each_mb": str(fsync).lower()})
            return
        if sys.argv[2] == "clear":
            app_post("/chaos/disk/clear")
            return

    if cmd == "dbgate":
        n = _cli_int(sys.argv, 2, 2)
        app_post("/chaos/db_gate/set", {"max_inflight": n})
        return

    if cmd == "retrystorm":
        if sys.argv[2] == "on":
            qps = _cli_int(sys.argv, 3, 20)
            app_post("/chaos/retry_storm/start", {"qps": qps})
            return
        if sys.argv[2] == "off":
            app_post("/chaos/retry_storm/stop")
            return

    if cmd == "net":
        action = sys.argv[2]
        if action == "clear":
            clear_toxics()
            return
        if action == "latency":
            ms = _cli_int(sys.argv, 3, 200)
            clear_toxics()
            add_toxic("latency", "latency", {"latency": ms, "jitter": int(ms * 0.2)})
            mark("net_latency", True, ms)
            return
        if action == "reset_peer":
            clear_toxics()
            add_toxic("reset", "reset_peer", {})
            mark("net_reset_peer", True, 1)
            return
        if action == "bandwidth":
            kbps = _cli_int(sys.argv, 3, 64)
            clear_toxics()
            add_toxic("bandwidth", "bandwidth", {"rate": kbps})
            mark("net_bandwidth", True, kbps)
            return

    if cmd == "dns":
        if sys.argv[2] == "bad":
            app_post("/chaos/dns/set_server", {"server": "203.0.113.123"})
            return
        if sys.argv[2] == "ok":
            app_post("/chaos/dns/set_server", {"server": ""})
            return

    usage()
    sys.exit(1)

if __name__ == "__main__":
    main()
