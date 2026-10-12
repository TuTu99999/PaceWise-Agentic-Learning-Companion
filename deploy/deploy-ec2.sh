#!/usr/bin/env bash
set -Eeuo pipefail

readonly DEPLOY_DIR="/opt/pacewise"
readonly COMPOSE_FILE="$DEPLOY_DIR/docker-compose.yml"
readonly RUNTIME_ENV="$DEPLOY_DIR/runtime.env"
readonly RELEASE_ENV="$DEPLOY_DIR/release.env"
readonly PREVIOUS_ENV="$DEPLOY_DIR/release.previous.env"
readonly LOCK_FILE="$DEPLOY_DIR/deploy.lock"

: "${AWS_REGION:?AWS_REGION is required}"
: "${BACKEND_IMAGE:?BACKEND_IMAGE is required}"
: "${FRONTEND_IMAGE:?FRONTEND_IMAGE is required}"
: "${IMAGE_TAG:?IMAGE_TAG is required}"

if [[ ! -s "$RUNTIME_ENV" ]]; then
  echo "Missing $RUNTIME_ENV. Copy runtime.env.example once and insert real secrets before deploying." >&2
  exit 1
fi

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "Another PaceWise deployment is already running." >&2
  exit 1
fi

compose() {
  docker compose \
    --project-directory "$DEPLOY_DIR" \
    --env-file "$RUNTIME_ENV" \
    --env-file "$RELEASE_ENV" \
    -f "$COMPOSE_FILE" "$@"
}

rollback() {
  local exit_code=$?
  trap - ERR
  echo "Release $IMAGE_TAG failed; attempting rollback." >&2
  if [[ -s "$PREVIOUS_ENV" ]]; then
    cp "$PREVIOUS_ENV" "$RELEASE_ENV"
    compose pull backend worker notification-worker frontend || true
    compose up -d --remove-orphans || true
    echo "Previous image set restored." >&2
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
compose pull postgres qdrant backend worker notification-worker frontend
compose up -d --remove-orphans postgres qdrant backend worker notification-worker frontend

for attempt in $(seq 1 36); do
  if curl --fail --silent --show-error --max-time 3 http://127.0.0.1/ >/dev/null \
    && compose exec -T backend python -c \
      "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=3)"; then
    rm -f "$PREVIOUS_ENV"
    trap - ERR
    echo "PaceWise release $IMAGE_TAG is healthy."
    compose ps
    exit 0
  fi
  sleep 5
done

echo "Health checks did not pass within 180 seconds." >&2
false
