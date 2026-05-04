#!/bin/sh
set -e

if [ $# -eq 0 ]; then
    exec python -m agent --help
fi

# When S3 offload is enabled, use the Python supervisor for SIGTERM-aware sync.
if [ "${S3_OFFLOAD_ENABLED:-0}" = "1" ]; then
    exec python -m infra.entrypoint_supervisor "$@"
fi

exec "$@"
