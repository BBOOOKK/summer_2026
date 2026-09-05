# 多仿真平台接入

任务逻辑只维护一份：`moveit_pick_place_node` 始终通过 MoveIt 2 和稳定的
ROS 2 接口执行。Gazebo Fortress 是当前权威验收后端；Isaac Sim、Webots
和 CoppeliaSim 只需适配传输层，不能复制或修改抓放状态机。

## 接口契约

`config/backend_contracts.yaml` 定义 `pick_place_ros2_v1`。任何后端必须提供：

- `/joint_states`；
- 机械臂和夹爪的 `FollowJointTrajectory` Action；
- `/pick_place/start`、`/pick_place/stop`、`/pick_place/reset_safety`；
- 目标物查询/复位、接触门控 attach/detach 和碰撞监控 readiness 服务。

后端运行后执行：

```bash
ros2 run robot_pick_place_sim backend_contract_check --ros-args \
  -p backend:=fortress -p timeout_sec:=30.0
```

缺少任一端点或类型不匹配都会以退出码 2 失败，避免“话题名字看起来差不多”
却在运行中静默失效。

## 平台映射

| 平台 | 原生 ROS 2 能力 | 需要补的薄适配层 | 本仓库状态 |
|---|---|---|---|
| Gazebo Fortress | `ros_gz_bridge`、`gz_ros2_control` | 接触、实体状态、可拆关节规范化 | 5/5 权威验收通过 |
| NVIDIA Isaac Sim | ROS 2 Bridge、Joint State、Articulation Controller | `FollowJointTrajectory` Action、实体/接触服务 | 接口契约就绪，未在本机执行 |
| Webots | `webots_ros2_control` | Supervisor 实体状态与接触服务 | 接口契约就绪，未在本机执行 |
| CoppeliaSim | `simROS2` topic/service/action API | 轨迹 Action 与实体/接触脚本 | 接口契约就绪，未在本机执行 |

Isaac Sim 的 Action Graph 应发布仿真时钟和 `/joint_states`，并把关节命令送入
Articulation Controller；Webots 使用同一 ros2_control 控制器 YAML；CoppeliaSim
场景脚本通过 `simROS2` 创建同名 topic、service 和 action。三个平台都必须重新跑
5 次动态验收后，才能把状态从 `connector_ready_not_executed` 改成
`acceptance_authoritative`。

平台依据：

- [Isaac Sim ROS 2 Joint Control](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/ros2_tutorials/tutorial_ros2_manipulation.html)
- [webots_ros2_control (ROS 2 Humble)](https://docs.ros.org/en/humble/p/webots_ros2_control/)
- [CoppeliaSim ROS 2 Interface](https://manual.coppeliarobotics.com/en/ros2Interface.htm)
