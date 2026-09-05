# 机械臂定点抓取仿真

面向“机器人集成小组项目 I”的 ROS 2 Humble 仿真包。权威后端为 Gazebo Fortress + MoveIt 2，系统使用 mechArm 270 教学模型，在固定 A 点抓取 50 g 标准块并放入固定 B 区，不使用视觉定位。真机阶段可保留 `/arm_controller/follow_joint_trajectory`、`/gripper_controller/follow_joint_trajectory`、`/pick_place/start`、`/pick_place/stop` 和 `/pick_place/state` 接口，只替换硬件及参数。

## 已实现

- 6 关节机械臂、双指对称平行夹爪、固定底座、桌面、A/B 标记与目标物；
- 回零 → A 点上方 → 下降 → 夹取 → 抬升 → B 点上方 → 下降 → 释放 → 抬升 → 回零；
- 单一 `fortress_moveit.launch.py` 启动 Gazebo、MoveIt、模型、控制器、状态和任务节点；
- 不可达、缺少示教/逆解、关节超限、Action 超时/拒绝、人工停止的安全停止；
- `/joint_states` 轨迹 CSV、每次执行结果 JSONL、错误 JSONL；
- 自动连续 5 次验收及 `acceptance_summary.json`。
- 左右指新鲜接触门控的 Gazebo 可拆 `fixed joint`；运输期间目标物位姿写入为 0；
- 每轮独立记录目标物的位置、姿态和速度轨迹。
- 桌面/目标/机器人三路实时接触审计，禁碰和数据源中断均锁存停机；
- 安全复位需要健康数据源和 1 s 无禁碰静默窗口，任务/监控双锁存同步复位。

## Ubuntu 22.04 快速启动

```bash
mkdir -p ~/robot_ws/src
cp -r robot_pick_place_sim ~/robot_ws/src/
cp -r robot_grasp_joint ~/robot_ws/src/
cd ~/robot_ws
source /opt/ros/humble/setup.bash
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
source install/setup.bash
ros2 launch robot_pick_place_sim fortress_moveit.launch.py
```

默认等待控制器就绪后自动执行一次。完整依赖、手动运行、连续 5 次验收和异常注入见 [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md)，实验记录见 [docs/SIMULATION_REPORT.md](docs/SIMULATION_REPORT.md)。
碰撞规则、锁存停机与动态注入结果见 [docs/COLLISION_SAFETY.md](docs/COLLISION_SAFETY.md)。

2026-09-05 Fortress + MoveIt 2 正式动态验收结果为 5/5；见 [权威运行说明](docs/fortress_moveit.md) 和 [机器可读证据](docs/evidence/fortress_moveit_acceptance_20260905.json)。

Isaac Sim、Webots 和 CoppeliaSim 的复用边界、接口映射及运行时契约检查见 [多仿真平台接入](docs/MULTI_SIM_BACKENDS.md)。未在本机执行的平台明确标记为未验收，不与 Fortress 的 5/5 结果混淆。

非 ROS 主机可执行：

```bash
python3 scripts/static_validate.py
```
