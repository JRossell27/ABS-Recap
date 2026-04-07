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
POST_DEPLOY_WAIT_SECONDS="${POST_DEPLOY_WAIT_SECONDS:-10}"
POST_DEPLOY_MAX_CHECKS="${POST_DEPLOY_MAX_CHECKS:-12}"
MIN_RUNNING_MACHINES="${MIN_RUNNING_MACHINES:-2}"

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
ensure_routable_machine() {
  local check=1
  while [[ $check -le $POST_DEPLOY_MAX_CHECKS ]]; do
    echo "Post-deploy machine check $check/$POST_DEPLOY_MAX_CHECKS..."

    set +e
    machine_rows="$(flyctl machine list -a "$APP" --json 2>/dev/null)"
    machine_status=$?
    set -e

    if [[ $machine_status -eq 0 ]]; then
      started_count="$(python - <<'PY' "$machine_rows"
import json, sys
rows = json.loads(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].strip() else []
started = 0
for row in rows:
    state = str(row.get("state", "")).lower()
    if state == "started":
        started += 1
print(started)
PY
)"

      if [[ "${started_count:-0}" -ge "$MIN_RUNNING_MACHINES" ]]; then
        echo "Found ${started_count} started machine(s); app should be routable."
        return 0
      fi

      machine_id_to_start="$(python - <<'PY' "$machine_rows"
import json, sys
rows = json.loads(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].strip() else []
candidate = ""
for row in rows:
    state = str(row.get("state", "")).lower()
    if state in {"stopped", "created", "starting"}:
        candidate = row.get("id", "") or candidate
if candidate:
    print(candidate)
PY
)"
      if [[ -n "${machine_id_to_start:-}" ]]; then
        echo "Only ${started_count:-0} started machine(s); attempting to start machine ${machine_id_to_start}."
        flyctl machine start "$machine_id_to_start" -a "$APP" || true
      else
        echo "No existing machine available to start; requesting Fly to keep ${MIN_RUNNING_MACHINES} machines running."
        flyctl scale count "$MIN_RUNNING_MACHINES" -a "$APP" || true
      fi
    else
      echo "Unable to list machines yet; retrying."
    fi

    sleep "$POST_DEPLOY_WAIT_SECONDS"
    check=$((check + 1))
  done

  echo "No started machines found after deploy checks."
  return 1
}

while [[ $attempt -le $MAX_ATTEMPTS ]]; do
  echo "Deploy attempt $attempt/$MAX_ATTEMPTS..."
  set +e
  output="$(flyctl deploy -a "$APP" --image "$IMAGE" --depot-scope="$SCOPE" --config "$CONFIG" 2>&1)"
  status=$?
  set -e

  echo "$output"

  if [[ $status -eq 0 ]]; then
    echo "Deploy succeeded; validating routable machine state..."
    if ensure_routable_machine; then
      exit 0
    fi
    echo "Deploy completed but no started machine became routable."
    exit 1
  fi

  if grep -qi "lease currently held\|proxy request failed.*no known healthy instances\|could not find a good candidate" <<<"$output"; then
    if [[ $attempt -lt $MAX_ATTEMPTS ]]; then
      echo "Transient Fly routing/lease issue detected; waiting ${SLEEP_SECONDS}s before retry..."
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
