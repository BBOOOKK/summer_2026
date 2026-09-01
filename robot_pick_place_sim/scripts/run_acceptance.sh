#!/usr/bin/env bash
set -euo pipefail

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

STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="${1:-$WORKSPACE/acceptance_logs/$STAMP}"
mkdir -p "$LOG_DIR"
LAUNCH_LOG="$LOG_DIR/launch_console.log"

ros2 launch robot_pick_place_sim simulation.launch.py \
  gui:=false auto_start:=false log_directory:="$LOG_DIR" \
  >"$LAUNCH_LOG" 2>&1 &
LAUNCH_PID=$!
cleanup() {
  kill -INT "$LAUNCH_PID" 2>/dev/null || true
  wait "$LAUNCH_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

for _attempt in $(seq 1 45); do
  if ros2 service type /pick_place/start 2>/dev/null | grep -q std_srvs; then
    break
  fi
  sleep 1
done
if ! ros2 service type /pick_place/start 2>/dev/null | grep -q std_srvs; then
  echo "Simulation failed to become ready; inspect $LAUNCH_LOG" >&2
  exit 3
fi

ros2 run robot_pick_place_sim acceptance_runner --ros-args \
  -p repeat_count:=5 -p log_directory:="$LOG_DIR"

python3 - "$LOG_DIR/acceptance_summary.json" <<'PY'
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
summary = json.loads(path.read_text(encoding='utf-8'))
print(json.dumps({
    'passed': summary['passed'],
    'succeeded': summary['succeeded'],
    'required_runs': summary['required_runs'],
    'evidence_passed': summary['evidence']['passed'],
    'report': str(path),
}, indent=2, ensure_ascii=False))
raise SystemExit(0 if summary['passed'] else 1)
PY
