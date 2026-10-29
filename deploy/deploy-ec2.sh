#!/usr/bin/env bash
set -Eeuo pipefail

readonly DEPLOY_DIR="/opt/pacewise"
readonly COMPOSE_FILE="$DEPLOY_DIR/docker-compose.yml"
readonly RUNTIME_ENV="$DEPLOY_DIR/runtime.env"
readonly SECRETS_ENV="$DEPLOY_DIR/secrets.env"
readonly RELEASE_ENV="$DEPLOY_DIR/release.env"
readonly PREVIOUS_ENV="$DEPLOY_DIR/release.previous.env"
readonly LOCK_FILE="$DEPLOY_DIR/deploy.lock"

: "${AWS_REGION:?AWS_REGION is required}"
: "${BACKEND_IMAGE:?BACKEND_IMAGE is required}"
: "${FRONTEND_IMAGE:?FRONTEND_IMAGE is required}"
: "${IMAGE_TAG:?IMAGE_TAG is required}"
: "${OPENAI_SECRET_ID:?OPENAI_SECRET_ID is required}"

if [[ ! -s "$RUNTIME_ENV" ]]; then
  echo "Missing $RUNTIME_ENV. Copy runtime.env.example once and insert real secrets before deploying." >&2
  exit 1
fi

pacewise_domain="$(sed -n 's/^PACEWISE_DOMAIN=//p' "$RUNTIME_ENV" | tail -n 1 | tr -d '\r')"
if [[ ! "$pacewise_domain" =~ ^[A-Za-z0-9.-]+$ || "$pacewise_domain" != *.* ]]; then
  echo "PACEWISE_DOMAIN must be a valid hostname in $RUNTIME_ENV." >&2
  exit 1
fi

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "Another PaceWise deployment is already running." >&2
  exit 1
fi

refresh_openai_secret() {
  local candidate
  candidate="$(mktemp "$DEPLOY_DIR/secrets.env.XXXXXX")"
  chmod 0600 "$candidate"

  if ! aws secretsmanager get-secret-value \
    --region "$AWS_REGION" \
    --secret-id "$OPENAI_SECRET_ID" \
    --query SecretString \
    --output text \
    | python3 -c '
import json
import sys

raw = sys.stdin.read()
try:
    payload = json.loads(raw)
except json.JSONDecodeError:
    value = raw.strip()
else:
    if not isinstance(payload, dict):
        raise SystemExit("OpenAI secret must be a JSON object or plaintext key")
    value = payload.get("OPENAI_API_KEY", "")

if not isinstance(value, str):
    raise SystemExit("OPENAI_API_KEY must be a string")
value = value.strip()
if not value or value.startswith("CHANGE_ME") or any(char in value for char in "\r\n\0"):
    raise SystemExit("OPENAI_API_KEY is missing or invalid")
sys.stdout.write(f"OPENAI_API_KEY={value}\n")
' > "$candidate"; then
    rm -f "$candidate"
    echo "Could not load OPENAI_API_KEY from AWS Secrets Manager." >&2
    return 1
  fi

  chown root:root "$candidate"
  mv "$candidate" "$SECRETS_ENV"
}

refresh_openai_secret

compose() {
  docker compose \
    --project-directory "$DEPLOY_DIR" \
    --env-file "$RUNTIME_ENV" \
    --env-file "$RELEASE_ENV" \
    -f "$COMPOSE_FILE" "$@"
}

print_diagnostics() {
  echo "PaceWise deployment diagnostics (secrets and environment values omitted):" >&2
  compose ps >&2 || true
  echo "Backend readiness response:" >&2
  compose exec -T backend python -c \
    "import http.client; c=http.client.HTTPConnection('127.0.0.1',8000,timeout=3); c.request('GET','/readyz'); r=c.getresponse(); print(r.status, r.read().decode())" \
    >&2 || true
  echo "Recent migration logs:" >&2
  compose logs --no-color --tail 80 migrate >&2 || true
  echo "Recent backend logs:" >&2
  compose logs --no-color --tail 120 backend >&2 || true
}

wait_until_healthy() {
  local attempts="${1:-36}"
  for attempt in $(seq 1 "$attempts"); do
    if curl --fail --silent --show-error --max-time 5 \
        --resolve "${pacewise_domain}:443:127.0.0.1" \
        "https://${pacewise_domain}/api/v1/status" >/dev/null \
      && compose exec -T backend python -c \
        "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=3)"; then
      return 0
    fi
    sleep 5
  done
  return 1
}

rollback() {
  local exit_code=$?
  trap - ERR
  echo "Release $IMAGE_TAG failed; attempting rollback." >&2
  print_diagnostics
  if [[ -s "$PREVIOUS_ENV" ]]; then
    cp "$PREVIOUS_ENV" "$RELEASE_ENV"
    compose pull backend worker notification-worker frontend caddy || true
    compose up -d --remove-orphans || true
    if wait_until_healthy 12; then
      echo "Previous image set restored and verified healthy." >&2
    else
      echo "Rollback image set is not healthy. Database migrations may not be backward compatible; manual recovery is required." >&2
      print_diagnostics
    fi
  else
    echo "No previous release exists; inspect container logs before retrying." >&2
  fi
  exit "$exit_code"
}
trap rollback ERR

registry="${BACKEND_IMAGE%%/*}"
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$registry"

if [[ -s "$RELEASE_ENV" ]]; then
  cp "$RELEASE_ENV" "$PREVIOUS_ENV"
else
  rm -f "$PREVIOUS_ENV"
fi

candidate="$(mktemp "$DEPLOY_DIR/release.env.XXXXXX")"
chmod 0600 "$candidate"
printf 'BACKEND_IMAGE=%s\nFRONTEND_IMAGE=%s\nIMAGE_TAG=%s\n' \
  "$BACKEND_IMAGE" "$FRONTEND_IMAGE" "$IMAGE_TAG" > "$candidate"
mv "$candidate" "$RELEASE_ENV"

compose config --quiet
compose pull postgres qdrant backend worker notification-worker frontend caddy
compose up -d --remove-orphans postgres qdrant backend worker notification-worker frontend caddy

if wait_until_healthy 36; then
  rm -f "$PREVIOUS_ENV"
  trap - ERR
  echo "PaceWise release $IMAGE_TAG is healthy."
  compose ps
  exit 0
fi

echo "Health checks did not pass within 180 seconds." >&2
false
