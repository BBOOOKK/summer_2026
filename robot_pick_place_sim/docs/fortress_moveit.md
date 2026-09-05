# Gazebo Fortress + MoveIt 2 backend

This is the authoritative simulation backend for ROS 2 Humble.  The task
state machine and stable ROS 2 services are shared with the Classic and future
hardware backends; only transport, controller and workcell parameters differ.

## What is simulated

- a world-fixed mechArm 270 model and a 50 g standard target;
- a 1.2 x 0.8 m table, marked pickup point A and placement region B;
- OMPL collision-aware planning and execution through MoveIt 2;
- a fixed-jaw / moving-jaw gripper with bilateral contact confirmation;
- a Fortress detachable fixed joint created only after contact confirmation;
- three fail-closed collision-monitor inputs and measured object tracking.

The target starts at a staging position so that all joints can initialize.  At
the beginning of every run, `object_manager` performs the single authorized
pose reset to A.  It never writes the target pose during transport.

## Build and run

```bash
source /opt/ros/humble/setup.bash
colcon build --symlink-install \
  --packages-select robot_grasp_joint robot_pick_place_sim mecharm_moveit_config
source install/setup.bash
ros2 launch robot_pick_place_sim fortress_moveit.launch.py auto_start:=false
```

After `/collision_monitor/readiness` reports `success: true`, start one run:

```bash
ros2 service call /pick_place/start std_srvs/srv/Trigger '{}'
```

The expected ordered terminal state is `SUCCEEDED`.  Logs contain task events,
joint and object trajectories, contact episodes, results, errors and the final
collision-monitor summary.  A valid run must include both finger-target
contacts, object lift, placement inside B, no forbidden collision and healthy
contact sources.

## Backend-specific details

Fortress 6 starts its detachable joint in the attached state.  The adapter
therefore sends the required `ignition.msgs.Empty` startup detach command and
withholds healthy task interfaces until the plugin publishes `detached` on its
`ignition.msgs.StringMsg` state topic.  The adapter also normalizes Fortress
contact, entity-state and joint-state transports to the stable task APIs.

