#!/usr/bin/env bash
# Builds the backend image and verifies it behaves as a production artifact:
# runs as non-root, refuses unsafe production config, migrates, and serves health/readiness.
# Object storage is configured but not contacted (readiness covers the database only).
# Requires PostgreSQL reachable from containers at SMOKE_DATABASE_URL (database must exist).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="${IMAGE:-upcycling-backend:smoke}"
PORT="${SMOKE_PORT:-18000}"
DB_URL="${SMOKE_DATABASE_URL:-postgresql+psycopg://upcycling:upcycling@host.docker.internal:55432/upcycling_smoke}"
RUN=(docker run --rm --add-host=host.docker.internal:host-gateway)
SAFE_ENV=(
  -e "UPCYCLING_DATABASE_URL=$DB_URL"
  -e "UPCYCLING_SECRET_KEY=$(openssl rand -hex 32)"
  -e "UPCYCLING_PUBLIC_ORIGIN=https://smoke.example"
  -e "UPCYCLING_SMTP_HOST=smtp.smoke.example"
  -e "UPCYCLING_SMTP_FROM=Upcycling <no-reply@smoke.example>"
  -e "UPCYCLING_SMTP_STARTTLS=true"
  -e "UPCYCLING_STORAGE_ENDPOINT_URL=https://s3.smoke.example"
  -e "UPCYCLING_STORAGE_BUCKET=upcycling-smoke"
  -e "UPCYCLING_STORAGE_ACCESS_KEY_ID=smoke-access-key"
  -e "UPCYCLING_STORAGE_SECRET_ACCESS_KEY=$(openssl rand -hex 32)"
)

fail() { echo "docker-smoke: FAIL: $*" >&2; exit 1; }

if [[ "${SKIP_BUILD:-0}" != "1" ]]; then
  docker build -t "$IMAGE" "$ROOT/backend"
fi

uid="$("${RUN[@]}" "$IMAGE" id -u)"
[[ "$uid" != "0" ]] || fail "container runs as root"
echo "docker-smoke: runs as uid $uid"

if "${RUN[@]}" -e "UPCYCLING_DATABASE_URL=$DB_URL" "$IMAGE" \
  python -c "from app.config import Settings; Settings()" >/dev/null 2>&1; then
  fail "production image accepted the insecure default configuration"
fi
echo "docker-smoke: insecure production config is rejected"

"${RUN[@]}" "${SAFE_ENV[@]}" "$IMAGE" alembic upgrade head

cid="$(docker run -d --add-host=host.docker.internal:host-gateway -p "127.0.0.1:$PORT:8000" "${SAFE_ENV[@]}" "$IMAGE")"
trap 'docker rm -f "$cid" >/dev/null' EXIT

for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:$PORT/api/v1/health/ready" >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -fsS "http://127.0.0.1:$PORT/api/v1/health/ready" | grep -q '"ready"' || {
  docker logs "$cid" >&2
  fail "readiness check did not pass"
}
status="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/api/v1/openapi.json")"
[[ "$status" == "404" ]] || fail "OpenAPI docs are exposed in production (HTTP $status)"
status="$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
  -d '{"email":"a@example.com"}' "http://127.0.0.1:$PORT/api/v1/auth/login-requests")"
[[ "$status" == "403" ]] || fail "state-changing request without Origin was not rejected (HTTP $status)"

# The image must be able to decode HEIC (pi-heif's bundled libheif works on this platform).
"${RUN[@]}" "${SAFE_ENV[@]}" "$IMAGE" python -c \
  "import pi_heif; assert pi_heif.libheif_info()['decoders'], 'no HEIF decoder'" ||
  fail "HEIC decoding is unavailable in the image"
echo "docker-smoke: HEIC decoder available"

echo "docker-smoke: OK"
