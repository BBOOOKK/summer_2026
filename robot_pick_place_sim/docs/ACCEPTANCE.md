# 仿真运行与验收

## 1. 环境与构建

在 Ubuntu 22.04 / ROS 2 Humble 上安装：

```bash
sudo apt update
sudo apt install -y \
  ros-humble-desktop \
  ros-humble-gazebo-ros-pkgs \
  ros-humble-gazebo-ros2-control \
  ros-humble-ros2-control \
  ros-humble-ros2-controllers \
  ros-humble-xacro \
  python3-colcon-common-extensions \
  python3-rosdep
```

把本包放入工作空间的 `src/`，再执行：

```bash
cd ~/robot_ws
source /opt/ros/humble/setup.bash
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
source install/setup.bash
colcon test --packages-select robot_pick_place_sim
colcon test-result --verbose
```

## 2. 单次运行

```bash
mkdir -p ~/robot_ws/acceptance_logs
ros2 launch robot_pick_place_sim simulation.launch.py \
  log_directory:=$HOME/robot_ws/acceptance_logs
```

观察完整流程以及终端的 `SUCCEEDED`。另一个终端可检查接口：

```bash
source ~/robot_ws/install/setup.bash
ros2 topic echo /pick_place/state
ros2 topic echo /joint_states
ros2 service call /pick_place/stop std_srvs/srv/Trigger '{}'
```

## 3. 连续 5 次验收

终端 A 禁用自动单次任务：

```bash
ros2 launch robot_pick_place_sim simulation.launch.py \
  auto_start:=false \
  log_directory:=$HOME/robot_ws/acceptance_logs
```

控制器全部激活后，在终端 B 执行：

```bash
source ~/robot_ws/install/setup.bash
ros2 run robot_pick_place_sim acceptance_runner --ros-args \
  -p repeat_count:=5 \
  -p log_directory:=$HOME/robot_ws/acceptance_logs
```

合格条件是 `acceptance_summary.json` 中 `succeeded >= 4` 且 `passed: true`。同时目视确认无桌面、自碰撞或超限，并保留演示视频。

## 4. 不可达与关节超限

复制参数并只修改测试项：

```bash
cp ~/robot_ws/src/robot_pick_place_sim/config/pick_place.yaml /tmp/unreachable.yaml
sed -i 's/pick_point_xyz: \[0.22, 0.12, 0.02\]/pick_point_xyz: [0.80, 0.00, 0.02]/' /tmp/unreachable.yaml
ros2 launch robot_pick_place_sim simulation.launch.py \
  task_config:=/tmp/unreachable.yaml
```

期望 `/pick_place/state` 为 `SAFE_STOP`，错误包含 `unreachable radius`，机械臂不执行轨迹。关节超限测试可把 `/tmp/unreachable.yaml` 中任一 `pick_joints` 值改到对应上下限之外，期望错误包含 `exceeds`。

## 5. 日志证据

- `trajectory_<run_id>.csv`：时间、关节名、位置、速度；
- `results.jsonl`：运行结果、耗时和轨迹文件；
- `errors.jsonl`：不可达、超限、超时等错误；
- `acceptance_summary.json`：5 次验收汇总。

不要把未实际运行的记录填写为成功；视频、日志和报告中的运行编号应一致。
