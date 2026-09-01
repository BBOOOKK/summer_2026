# 机械臂定点抓取仿真

ROS 2 Humble + Gazebo Classic 教学包，面向 mechArm 270 固定 A 点抓取、B 区放置实验。任务逻辑不依赖视觉；真机阶段沿用相同控制接口，只替换设备与参数。

## 当前内容

- `urdf/mecharm270.urdf.xacro`：6 关节机械臂、平行夹爪、`gazebo_ros2_control`。
- `worlds/pick_place.world`：桌面、50 g 目标方块、绿色放置区。
- `config/pick_place.yaml`：A/B 点、安全高度、示教关节位姿、限位与超时。
- `config/controllers.yaml`：机械臂和夹爪轨迹控制器。

完整启动、异常测试和 5 次验收命令将在后续步骤补齐。
