# 仿真动态验证报告

验证日期：2026-09-01

验证版本：`8ad0c99e`（物理落点验收代码）；后续文档与证据提交不改变任务逻辑。

## 环境

- 宿主：macOS / Apple Silicon；
- Linux：Colima VZ，Ubuntu 22.04 amd64 容器，Rosetta 转译；
- ROS 2 Humble；
- Gazebo Classic 11.10.2；
- `gazebo_ros2_control` 0.4.10；
- 无界面物理运行，Gazebo GUI 不作为动态判定依据。

## 构建与自动测试

`colcon build --symlink-install` 成功。`colcon test` 共 9 项，结果为 9 passed、0 failed，覆盖 XML/场景、KDL 根链接、A/B 示教几何、安全高度、不可达、缺少解和关节超限。

## 五次物理抓放

验收器只有在以下条件同时成立时才计为成功：

1. 完整 Action 序列返回 `SUCCEEDED`；
2. `/gazebo/get_entity_state` 查询成功；
3. 方块最终 XY 坐标位于 B 区 0.07 m 半径内；
4. 方块最终高度位于 0.74–0.85 m；
5. 轨迹、结果和落点均写入证据文件。

结果为 5/5。五次最终坐标均为 `[0.2044, -0.1350, 0.7675] m`。完整数据见 [acceptance_summary.json](evidence/2026-09-01/acceptance_physical/acceptance_summary.json)，每次轨迹约 13,280 行。

## 碰撞审计

额外执行一次 28 秒完整抓放并订阅 Gazebo 物理接触流。29,292 条接触消息只有以下允许碰撞：

- 方块—桌面：15,437；
- 机械臂底座—桌面：13,855。

机械臂其他连杆—桌面、自碰撞等非预期碰撞为 0。原始接触流为 139,003,842 字节，不提交 Git；其 SHA-256、行数和碰撞对见 [contact_summary.json](evidence/2026-09-01/collision_audit/contact_summary.json)。

## 异常验证

| 异常 | 实际结果 | run_id |
| --- | --- | --- |
| A 点改为 `[0.80, 0.00, 0.02]` | 0.008 s 内 `SAFE_STOP`，目标物保持 A 点 | `20260901_025411_9d245b` |
| `joint4=3.000` 超限 | 验证阶段 `SAFE_STOP` | `20260901_025527_6df366` |
| 运行中调用 `/pick_place/stop` | 当前 Action 取消，发布 `STOPPING`、`SAFE_STOP` | `20260901_025607_e57034` |
| `pick_joints` 只有一个值 | 报告无六关节 IK/示教解并 `SAFE_STOP` | `20260901_025646_cbbf6e` |

错误、结果、短轨迹与 Launch 输出均保存在 `docs/evidence/2026-09-01/anomaly_*`。

## 视频说明

[demo_pick_place_20260901.mp4](evidence/2026-09-01/video/demo_pick_place_20260901.mp4) 是根据真实 Gazebo 运行 `20260901_025053_5a7eb2` 的 `/joint_states` 轨迹生成的可复现双视图动画，规格为 H.264、1280×720、15 fps、18.934 秒。画面明确标注数据来源；它不是 Gazebo GUI 录屏。生成命令：

```bash
python3 scripts/render_trajectory_video.py \
  --input docs/evidence/2026-09-01/acceptance_physical/trajectory_20260901_025053_5a7eb2.csv \
  --output docs/evidence/2026-09-01/video/demo_pick_place_20260901.mp4
```

生成环境需要 Pillow 与 ffmpeg。在 Ubuntu 可安装 `python3-pil ffmpeg`。
