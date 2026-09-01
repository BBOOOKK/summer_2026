# robot_grasp_joint

Gazebo Classic 11 中的接触门控、可拆 fixed-joint 抓持后端。它用于替代运输阶段
100 Hz `SetEntityState` 位姿跟随，同时保留释放后的真实重力下落。

## 接口

- `/grasp/attach` (`std_srvs/srv/Trigger`)：检查目标距离和近期双指接触后，在
  `mecharm270::tool0` 与 `target_object::object` 之间创建 Gazebo `fixed` joint。
- `/grasp/detach` (`std_srvs/srv/Trigger`)：拆除 joint 并显式唤醒负载，使重力立即生效。
- `/grasp/status` (`std_srvs/srv/Trigger`)：返回附着、模型、接触、距离和计数状态。
- `/grasp/state` (`std_msgs/msg/String`)：每次命令完成时发布 JSON 结果。

物理对象操作只在 Gazebo `WorldUpdateBegin` 回调中执行；ROS 服务线程仅排队并等待
结果，避免从 ROS executor 线程直接修改 ODE 世界。

## 加载

`models/grasp_plugin_carrier/model.sdf` 是不带碰撞几何的静态载体，可在原仿真已启动后
动态插入，因此不要求向机械臂 URDF 添加插件：

```bash
ros2 launch robot_grasp_joint spawn_grasp_plugin.launch.py
```

正式任务配置样例为 `config/task_service_grasp.yaml`。其中 `attachment_mode=service`，
夹爪先真实闭合；任务确认左右指尖接触后调用 `/grasp/attach`，到 RELEASE 前调用
`/grasp/detach`。每轮开始使用一次 `SetEntityState` 将试件复位到 A 点仍可保留；运输
期间不再写目标物位姿。

## 独立 smoke 验证

`worlds/grasp_joint_smoke.world` 会自动把 80 g 负载附着在固定夹持点。启动后在另一终端
运行验证器：

```bash
ros2 launch gazebo_ros gazebo.launch.py \
  world:=$(ros2 pkg prefix robot_grasp_joint)/share/robot_grasp_joint/worlds/grasp_joint_smoke.world \
  gui:=false

ros2 run robot_grasp_joint verify_grasp_joint.py
```

通过时输出 `GRASP_JOINT_SMOKE_PASS`；验证器要求附着期间高度漂移小于 0.1 mm，拆除后
至少下落 0.2 m。
