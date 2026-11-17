#!/usr/bin/env bash
# CI only: starts SeaweedFS (S3-compatible, same version and credentials as compose.yaml).
# GitHub Actions service containers cannot pass a command, so it runs as a plain container.
set -euo pipefail

docker run -d --name upcycling-storage -p 8333:8333 \
  -e AWS_ACCESS_KEY_ID=upcycling-dev \
  -e AWS_SECRET_ACCESS_KEY=upcycling-dev-storage-secret \
  chrislusf/seaweedfs:4.52 mini -dir=/data -ip.bind=0.0.0.0 -admin.ui=false

for _ in $(seq 1 60); do
  if curl -fsS -o /dev/null http://localhost:8333/healthz; then
    echo "storage ready"
    exit 0
  fi
  sleep 1
done
docker logs upcycling-storage >&2
exit 1
