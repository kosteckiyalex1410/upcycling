#!/usr/bin/env bash
# Local HTTPS environment for testing the PWA on a real iPhone on the same Wi-Fi.
# Development only; see "Testing on a real iPhone" in docs/development.md.
#
#   scripts/iphone.sh up     build the PWA, start the HTTPS proxy, allow the origin in storage CORS
#   scripts/iphone.sh api    run the API for the iPhone (foreground, reload) on 127.0.0.1:$API_PORT
#   scripts/iphone.sh check  verify certificate, app, API and storage CORS from this Mac
#   scripts/iphone.sh down   stop the proxy and restore the localhost-only storage CORS rule
#
# The LAN name defaults to this Mac's Bonjour name (<LocalHostName>.local), which stays the
# same across networks; override with UPCYCLING_LAN_HOST (e.g. the Wi-Fi IP address).
set -euo pipefail
cd "$(dirname "$0")/.."

LAN_HOST="${UPCYCLING_LAN_HOST:-$(scutil --get LocalHostName | tr '[:upper:]' '[:lower:]').local}"
API_PORT="${UPCYCLING_IPHONE_API_PORT:-8010}"
APP_ORIGIN="https://${LAN_HOST}:8443"
STORAGE_ORIGIN="https://${LAN_HOST}:8444"
CERT_DIR=.dev-iphone
CERT="$CERT_DIR/upcycling-dev-root.crt"
CA_PATH=/data/caddy/pki/authorities/local/root.crt
if [[ -z "${PNPM:-}" ]]; then
  if command -v pnpm >/dev/null; then PNPM=pnpm; else PNPM="corepack pnpm"; fi
fi
export UPCYCLING_LAN_HOST="$LAN_HOST" UPCYCLING_IPHONE_API_PORT="$API_PORT"

# Settings for the API process that serves the iPhone; they override `.env`. Secure
# `__Host-` cookie as in production. localhost:5173 stays allowed so the regular
# `make dev-web` keeps uploading while the iPhone setup runs (shared bucket CORS rule).
iphone_settings() {
  export UPCYCLING_PUBLIC_ORIGIN="$APP_ORIGIN"
  export UPCYCLING_EXTRA_ALLOWED_ORIGINS='["http://localhost:5173"]'
  export UPCYCLING_SESSION_COOKIE_SECURE=true
  export UPCYCLING_STORAGE_PUBLIC_ENDPOINT_URL="$STORAGE_ORIGIN"
}

compose() { docker compose --profile iphone "$@"; }

up() {
  echo "==> Building the PWA (production build, service worker included)"
  $PNPM --filter @upcycling/expert-pwa build >/dev/null
  echo "==> Starting local services and the HTTPS proxy for ${LAN_HOST}"
  compose up -d --wait db mailpit storage
  compose up -d --force-recreate iphone-proxy
  echo "==> Allowing ${APP_ORIGIN} to upload to storage (bucket CORS)"
  (iphone_settings && cd backend && uv run python -m app.cli storage-init)

  for _ in $(seq 1 30); do
    compose exec -T iphone-proxy test -f "$CA_PATH" 2>/dev/null && break
    sleep 1
  done
  mkdir -p "$CERT_DIR"
  compose cp "iphone-proxy:$CA_PATH" "$CERT" >/dev/null
  # Wait until Caddy has issued the site certificates.
  for _ in $(seq 1 30); do
    curl -fsS -o /dev/null --cacert "$CERT" "$APP_ORIGIN/" 2>/dev/null && break
    sleep 1
  done
  summary
}

summary() {
  cat <<EOF

iPhone test environment is up (reachable from this Wi-Fi network only).

  Open on the iPhone:   ${APP_ORIGIN}/
  Root certificate:     $(pwd)/${CERT}
  SHA-256 fingerprint:  $(openssl x509 -noout -fingerprint -sha256 -in "$CERT" | cut -d= -f2)

Next:
  1. In another terminal: make iphone-api   (keep it running)
  2. make iphone-check
  3. First time only: AirDrop the root certificate to the iPhone and trust it
     (docs/development.md, "Testing on a real iPhone").
  4. Sign-in codes arrive in Mailpit on this Mac: http://localhost:8025
EOF
}

api() {
  iphone_settings
  echo "API for ${APP_ORIGIN} on 127.0.0.1:${API_PORT} (presigned uploads go to ${STORAGE_ORIGIN})"
  cd backend
  exec uv run uvicorn app.main:create_app --factory --reload --host 127.0.0.1 \
    --port "$API_PORT" --timeout-keep-alive 75
}

check() {
  local ok=1
  [[ -f "$CERT" ]] || { echo "No certificate yet; run: make iphone-up"; exit 1; }
  if curl -fsS --cacert "$CERT" "$APP_ORIGIN/" | grep -q '<div id="root">'; then
    echo "ok   PWA over HTTPS at ${APP_ORIGIN}/ (certificate chains to the dev root)"
  else
    echo "FAIL PWA not reachable at ${APP_ORIGIN}/ (is the proxy up? does ${LAN_HOST} resolve?)"
    ok=0
  fi
  if curl -fsS --cacert "$CERT" "$APP_ORIGIN/api/v1/health" | grep -q '"ok"'; then
    echo "ok   API reachable through the proxy"
  else
    echo "FAIL API not reachable; is 'make iphone-api' running?"
    ok=0
  fi
  local bucket allow
  bucket="$(grep -E '^UPCYCLING_STORAGE_BUCKET=' .env 2>/dev/null | cut -d= -f2)"
  allow="$(curl -sS --cacert "$CERT" -o /dev/null -D - -X OPTIONS \
    -H "Origin: ${APP_ORIGIN}" -H 'Access-Control-Request-Method: PUT' \
    -H 'Access-Control-Request-Headers: content-type,x-amz-checksum-sha256' \
    "${STORAGE_ORIGIN}/${bucket:-upcycling}/uploads/check" |
    tr -d '\r' | awk -F': ' 'tolower($1)=="access-control-allow-origin"{print $2}')"
  if [[ "$allow" == "$APP_ORIGIN" ]]; then
    echo "ok   storage at ${STORAGE_ORIGIN} accepts uploads from ${APP_ORIGIN} (CORS)"
  else
    echo "FAIL storage CORS does not allow ${APP_ORIGIN}; run: make iphone-up"
    ok=0
  fi
  [[ $ok == 1 ]]
}

down() {
  compose rm -sf iphone-proxy
  echo "==> Restoring the storage CORS rule from .env (localhost only)"
  (cd backend && uv run python -m app.cli storage-init)
}

case "${1:-}" in
  up) up ;;
  api) api ;;
  check) check ;;
  down) down ;;
  url) echo "${APP_ORIGIN}/" ;;
  *) echo "Usage: $0 up|api|check|down|url" >&2; exit 2 ;;
esac
