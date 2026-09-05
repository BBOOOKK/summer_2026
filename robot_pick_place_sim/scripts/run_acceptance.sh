#!/usr/bin/env bash
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
if [[ -n "${ROBOT_WS:-}" ]]; then
  WORKSPACE="$ROBOT_WS"
elif [[ "$(basename "$(dirname "$PACKAGE_DIR")")" == "src" ]]; then
  WORKSPACE="$(cd "$PACKAGE_DIR/../.." && pwd)"
else
  echo "Set ROBOT_WS to the built ROS 2 workspace (for example ~/robot_ws)." >&2
  exit 2
fi

source /opt/ros/humble/setup.bash
source "$WORKSPACE/install/setup.bash"
set -u

STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="${1:-$WORKSPACE/acceptance_logs/$STAMP}"
mkdir -p "$LOG_DIR"
LAUNCH_LOG="$LOG_DIR/launch_console.log"

BACKEND="${BACKEND:-fortress}"
REPEAT_COUNT="${REPEAT_COUNT:-5}"
case "$BACKEND" in
  fortress)
    LAUNCH_FILE="fortress_moveit.launch.py"
    LAUNCH_ARGS=(auto_start:=false log_directory:="$LOG_DIR")
    ;;
  classic)
    LAUNCH_FILE="simulation.launch.py"
    LAUNCH_ARGS=(gui:=false auto_start:=false log_directory:="$LOG_DIR")
    ;;
  *)
    echo "Unsupported backend '$BACKEND' (expected fortress or classic)." >&2
    exit 2
    ;;
esac

ros2 launch robot_pick_place_sim "$LAUNCH_FILE" "${LAUNCH_ARGS[@]}" \
  >"$LAUNCH_LOG" 2>&1 &
LAUNCH_PID=$!
cleanup() {
  kill -INT "$LAUNCH_PID" 2>/dev/null || true
  wait "$LAUNCH_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

for _attempt in $(seq 1 90); do
  if ros2 service type /pick_place/start 2>/dev/null | grep -q std_srvs; then
    break
  fi
  sleep 1
done
if ! ros2 service type /pick_place/start 2>/dev/null | grep -q std_srvs; then
  echo "Simulation failed to become ready; inspect $LAUNCH_LOG" >&2
  exit 3
fi

for _attempt in $(seq 1 60); do
  READINESS="$(ros2 service call /collision_monitor/readiness \
    std_srvs/srv/Trigger '{}' 2>/dev/null || true)"
  if grep -q 'success=True' <<<"$READINESS"; then
    break
  fi
  sleep 1
done
if ! grep -q 'success=True' <<<"${READINESS:-}"; then
  echo "Collision monitor failed readiness; inspect $LAUNCH_LOG" >&2
  exit 4
fi

ros2 run robot_pick_place_sim acceptance_runner --ros-args \
  -p repeat_count:="$REPEAT_COUNT" -p log_directory:="$LOG_DIR" \
  -p backend:="$BACKEND"

python3 - "$LOG_DIR/acceptance_summary.json" <<'PY'
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
summary = json.loads(path.read_text(encoding='utf-8'))
print(json.dumps({
    'backend': summary['backend'],
    'passed': summary['passed'],
    'succeeded': summary['succeeded'],
    'required_runs': summary['required_runs'],
    'evidence_passed': summary['evidence']['passed'],
    'report': str(path),
}, indent=2, ensure_ascii=False))
raise SystemExit(0 if summary['passed'] else 1)
PY
