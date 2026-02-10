#!/usr/bin/env bash
set -euo pipefail

mkdir -p /data/syscalls /data/events /data/logs

ENABLE_STRACE="${ENABLE_STRACE:-1}"
STRACE_FILTER="${STRACE_FILTER:-%network,%file,%process,%desc,%signal}"

echo "$(date -Is) starting app (ENABLE_STRACE=${ENABLE_STRACE})" | tee -a /data/logs/entrypoint.log

if [[ "${ENABLE_STRACE}" == "1" ]]; then
  echo "$(date -Is) running uvicorn under strace filter=${STRACE_FILTER}" | tee -a /data/logs/entrypoint.log
  # strace writes per-thread files to /data/syscalls/trace.* with epoch timestamps + syscall durations.
  # uvicorn stdout/stderr are captured to /data/logs.
  strace -ff -ttt -T -s 200 -yy -e trace="${STRACE_FILTER}" -o /data/syscalls/trace \
    uvicorn main:app --host 0.0.0.0 --port 8000 \
    > /data/logs/app_stdout.log 2> /data/logs/app_stderr.log
else
  uvicorn main:app --host 0.0.0.0 --port 8000 \
    > /data/logs/app_stdout.log 2> /data/logs/app_stderr.log
fi

echo "$(date -Is) app exited" | tee -a /data/logs/entrypoint.log
