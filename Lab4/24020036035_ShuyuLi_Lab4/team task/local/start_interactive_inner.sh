#!/bin/bash
set -euo pipefail
SRC=$1
BASE=/opt/vnav-lab4
ip link set lo up
ip link add lab4nic type dummy
ip addr add 192.168.198.1/24 dev lab4nic
ip link set lab4nic up
ip route add default dev lab4nic
mountpoint -q "$BASE/focal/proc" || mount -t proc proc "$BASE/focal/proc"
mountpoint -q "$BASE/focal/dev" || mount --bind /dev "$BASE/focal/dev"
if [ ! -d "$BASE/simulator-interactive" ]; then cp -a "$BASE/simulator/lab4" "$BASE/simulator-interactive"; fi
cp "$SRC/local/interactive_assets/globalgamemanagers" "$BASE/simulator-interactive/lab4_Data/"
cp "$SRC/scripts/monitor_interactive.py" "$BASE/focal/work/lab4/scripts/"
cp "$SRC/scripts/read_flight_data.py" "$BASE/focal/work/lab4/scripts/"
cp "$SRC/scripts/race_timer.py" "$BASE/focal/work/lab4/scripts/"
cp "$SRC/scripts/rigid_reference_node.py" "$BASE/focal/work/lab4/scripts/"
cp "$SRC/scripts/record_race.py" "$BASE/focal/work/lab4/scripts/"
cp "$SRC/results/gates.json" "$BASE/focal/work/lab4/results/"
if [ "${LAB4_SUBSECOND:-}" = 1 ]; then
 if [ ! -d "$BASE/simulator-nointerp" ]; then cp -a "$BASE/simulator" "$BASE/simulator-nointerp"; fi
 cp "$SRC/local/interpolation_fix/level0" "$BASE/simulator-nointerp/lab4/lab4_Data/"
 cp "$SRC/local/interactive_assets/globalgamemanagers" "$BASE/simulator-nointerp/lab4/lab4_Data/"
 python3 - "$SRC" "$BASE" <<'PY'
import sys,json,re,shutil
from pathlib import Path
source=Path(sys.argv[1]);base=Path(sys.argv[2]);runtime=base/'focal/work/lab4'
profile=json.loads((source/'local/subsecond_profile.json').read_text())
reference=Path(profile['reference'])
(runtime/reference).parent.mkdir(parents=True,exist_ok=True)
for file in ['reference.csv','model_status.json']:
 shutil.copy2(source/reference.parent/file,runtime/reference.parent/file)
p=runtime/'ws/src/tesse-ros-bridge/ROS/launch'
s=(p/'tesse_quadrotor_bridge.launch').read_text().replace('to="/current_state"','to="/tesse/asynchronous_state"')
s=s.replace('<!-- Topics -->','<!-- Topics -->\n    <remap from="/clock" to="/tesse/asynchronous_clock"/>',1)
s=re.sub(r'<node\s+ns="\$\(arg ns\)"\s+name="quadrotor_control_interface"[\s\S]*?</node>','',s)
(p/'tesse_quadrotor_bridge_sync.launch').write_text(s)
PY
fi
export LAB4_BASE=$BASE DISPLAY=${LAB4_DISPLAY:-:0} LC_ALL=C LIBGL_ALWAYS_SOFTWARE=1 LP_NUM_THREADS=8
export XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir DISABLE_ROS1_EOL_WARNINGS=1
unset WAYLAND_DISPLAY
exec python3 "$SRC/local/interactive_app.py" --source "$SRC"
