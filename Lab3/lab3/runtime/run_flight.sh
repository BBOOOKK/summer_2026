#!/bin/bash
source /opt/ros/noetic/setup.bash
source /lab3/ros_ws/devel/setup.bash
run_dir=$(mktemp -d "${LAB3_FLIGHT_DIR:-/tmp}/lab3-flight.XXXXXX") || exit 1
echo "Flight output: $run_dir"
nohup python3 /lab3/runtime/ros_unity_bridge.py "_record_dir:=$run_dir" >"$run_dir/bridge.log" 2>&1 </dev/null &
nohup roslaunch controller_pkg traj_tracking.launch >"$run_dir/controller.log" 2>&1 </dev/null &
nohup python3 /lab3/ros_ws/src/controller_pkg/scripts/flight_visualizer.py >"$run_dir/visualizer.log" 2>&1 </dev/null &
