import os
import sys
import requests

APP = os.getenv("APP_BASE", "http://localhost:8000")
TOXI = os.getenv("TOXI_BASE", "http://localhost:8474")

def app_post(path, params=None):
    r = requests.post(f"{APP}{path}", params=params, timeout=5)
    print(r.status_code, r.text)
    r.raise_for_status()

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
    # Get existing toxics and delete them one by one
    proxies = toxi("GET", "/proxies") or {}
    downstream = proxies.get("downstream", {})
    toxics = downstream.get("toxics", [])
    for toxic in toxics:
        toxic_name = toxic.get("name", "")
        if toxic_name:
            try:
                toxi("DELETE", f"/proxies/downstream/toxics/{toxic_name}")
            except Exception:
                pass  # Ignore errors deleting individual toxics

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
            workers = int(sys.argv[3]) if len(sys.argv) > 3 else 2
            app_post("/chaos/cpu/start", {"workers": workers})
            return
        if sys.argv[2] == "off":
            app_post("/chaos/cpu/stop")
            return

    if cmd == "lock":
        if sys.argv[2] == "on":
            threads = int(sys.argv[3]) if len(sys.argv) > 3 else 80
            app_post("/chaos/lock_convoy/start", {"threads": threads})
            return
        if sys.argv[2] == "off":
            app_post("/chaos/lock_convoy/stop")
            return

    if cmd == "memleak":
        if sys.argv[2] == "on":
            rate = int(sys.argv[3]) if len(sys.argv) > 3 else 20
            app_post("/chaos/mem/leak/start", {"mb_per_sec": rate})
            return
        if sys.argv[2] == "off":
            app_post("/chaos/mem/leak/stop")
            return

    if cmd == "fdleak":
        if sys.argv[2] == "on":
            rate = int(sys.argv[3]) if len(sys.argv) > 3 else 200
            app_post("/chaos/fd/leak/start", {"rate_per_sec": rate})
            return
        if sys.argv[2] == "off":
            app_post("/chaos/fd/leak/stop")
            return

    if cmd == "disk":
        if sys.argv[2] == "fill":
            mb = int(sys.argv[3]) if len(sys.argv) > 3 else 200
            fsync = "--fsync" in sys.argv
            app_post("/chaos/disk/fill", {"mb": mb, "fsync_each_mb": str(fsync).lower()})
            return
        if sys.argv[2] == "clear":
            app_post("/chaos/disk/clear")
            return

    if cmd == "dbgate":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 2
        app_post("/chaos/db_gate/set", {"max_inflight": n})
        return

    if cmd == "retrystorm":
        if sys.argv[2] == "on":
            qps = int(sys.argv[3]) if len(sys.argv) > 3 else 20
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
            ms = int(sys.argv[3]) if len(sys.argv) > 3 else 200
            clear_toxics()
            add_toxic("latency", "latency", {"latency": ms, "jitter": int(ms * 0.2)})
            return
        if action == "reset_peer":
            clear_toxics()
            add_toxic("reset", "reset_peer", {})
            return
        if action == "bandwidth":
            kbps = int(sys.argv[3]) if len(sys.argv) > 3 else 64
            clear_toxics()
            add_toxic("bandwidth", "bandwidth", {"rate": kbps})
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
