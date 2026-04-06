#!/usr/bin/env bash
set -euo pipefail

# Retries Fly deploys that fail due to temporary machine lease contention.
#
# Usage:
#   ./scripts/fly_deploy_retry.sh \
#     --app abs-recap \
#     --image registry.fly.io/abs-recap:deployment-<tag> \
#     --config fly.toml

APP=""
IMAGE=""
CONFIG="fly.toml"
SCOPE="app"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-6}"
SLEEP_SECONDS="${SLEEP_SECONDS:-20}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app)
      APP="$2"
      shift 2
      ;;
    --image)
      IMAGE="$2"
      shift 2
      ;;
    --config)
      CONFIG="$2"
      shift 2
      ;;
    --depot-scope)
      SCOPE="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$APP" || -z "$IMAGE" ]]; then
  echo "Missing required args. Expected --app and --image." >&2
  exit 2
fi

attempt=1
while [[ $attempt -le $MAX_ATTEMPTS ]]; do
  echo "Deploy attempt $attempt/$MAX_ATTEMPTS..."
  set +e
  output="$(flyctl deploy -a "$APP" --image "$IMAGE" --depot-scope="$SCOPE" --config "$CONFIG" 2>&1)"
  status=$?
  set -e

  echo "$output"

  if [[ $status -eq 0 ]]; then
    echo "Deploy succeeded."
    exit 0
  fi

  if grep -qi "lease currently held" <<<"$output"; then
    if [[ $attempt -lt $MAX_ATTEMPTS ]]; then
      echo "Lease contention detected; waiting ${SLEEP_SECONDS}s before retry..."
      sleep "$SLEEP_SECONDS"
      attempt=$((attempt + 1))
      continue
    fi
  fi

  echo "Deploy failed with a non-retryable error."
  exit "$status"
done

echo "Deploy failed after $MAX_ATTEMPTS attempts due to repeated lease contention."
exit 1
