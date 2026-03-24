# Failure Zoo (Python) — syscalls + metrics persisted to ./data

This is a Docker Compose lab for generating reproducible failure modes and collecting:
- **Syscall traces** (via `strace` running inside the app container)
- **Application metrics** (`/metrics` Prometheus format)
- **System/container metrics** (cAdvisor)
- **Ground-truth labels** (JSONL events when chaos is toggled)

All data is stored in a `./data/` folder on your host so it remains after containers stop.

## Start
```bash
docker compose up -d --build
```

## URLs
- App health: http://localhost:8000/health
- App metrics: http://localhost:8000/metrics
- SOM learner health: http://localhost:8100/health
- SOM learner status: http://localhost:8100/status
- SOM learner signal: http://localhost:8100/signal
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)
- cAdvisor: http://localhost:8080
- Toxiproxy API: http://localhost:8474

## Trigger chaos
```bash
docker compose run --rm chaos cpu on 4
docker compose run --rm chaos cpu off

docker compose run --rm chaos lock on 150
docker compose run --rm chaos lock off

docker compose run --rm chaos memleak on 50
docker compose run --rm chaos memleak off

docker compose run --rm chaos fdleak on 200
docker compose run --rm chaos fdleak off

docker compose run --rm chaos disk fill 2000
docker compose run --rm chaos disk clear

docker compose run --rm chaos dbgate 1
docker compose run --rm chaos dbgate 10

docker compose run --rm chaos retrystorm on 50
docker compose run --rm chaos retrystorm off

docker compose run --rm chaos net latency 400
docker compose run --rm chaos net reset_peer
docker compose run --rm chaos net bandwidth 64
docker compose run --rm chaos net clear

docker compose run --rm chaos dns bad
curl "http://localhost:8000/dns/test?name=example.com"
docker compose run --rm chaos dns ok

docker compose run --rm chaos reset
```

## Persisted outputs (host)
- `./data/app/syscalls/trace.*` — syscall traces (epoch timestamps + duration)
- `./data/app/events/chaos_events.jsonl` — chaos on/off labels (epoch timestamps)
- `./data/app/logs/*` — app & strace logs
- `./data/learner/model/som_model.npz` — persisted SOM model
- `./data/learner/events/anomaly_events.jsonl` — SOM anomaly outputs
- `./data/prometheus/` — Prometheus TSDB blocks
- `./data/grafana/` — Grafana state
- `./data/postgres/` — Postgres data

## Stop (data remains)
```bash
docker compose down
```

## Delete data
```bash
rm -rf ./data
```

## Notes for macOS
`strace` runs inside the Linux container (Docker Desktop’s Linux VM kernel), so it works on macOS without installing any syscall tools on the host.


## Note: toxiproxy image
This project uses `ghcr.io/shopify/toxiproxy:latest` because the old Docker Hub `shopify/toxiproxy` repository is deprecated.


## Syscall tracing requirements
The app container enables `SYS_PTRACE` and disables the default seccomp profile so `strace` can run inside Docker.
