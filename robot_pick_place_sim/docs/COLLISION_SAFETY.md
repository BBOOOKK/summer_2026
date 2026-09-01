# 运行时碰撞安全闭环

## 策略

- Gazebo 独立发布桌面、目标物和机器人各链接的接触消息。
- `collision_monitor` 对每个接触对进行阶段相关分类：底座—桌面、目标物—桌面和抓取阶段的指端—目标物属于许可接触；机器人—桌面、非相邻自碰、非指端—目标物属于禁止接触。
- 三类接触源必须全部持续新鲜；未启动或超时均按故障处理（fail closed）。
- 首次禁止接触只触发一次 `/pick_place/collision_stop`，取消正在执行的 Action，拆除抓持关节并锁存停机。
- 未经显式复位，`/pick_place/start` 会一直拒绝新任务。复位前必须同时满足接触源健康和禁碰消失至少 1 s，任务节点与监控节点的双锁存才会一起清除。

## 动态故障注入证据

2026-09-01 将目标物注入 `link3/link1` 碰撞区域，实测结果：

- 禁止接触被识别为 `unexpected_monitored_contact`；
- `safe_stop_calls = 1`、`safe_stop_successes = 1`、`safe_stop_failures = 0`；
- 锁存后的 `/pick_place/start` 返回 `success=false`；
- 移除障碍、等待静默窗口并调用 `/pick_place/reset_safety` 后，健康检查恢复 `ready=true`；
- 复位后的完整抓取再次到达 `SUCCEEDED`。

运行证据保存为 `contacts.jsonl`、`collision_summary.json`、`errors.jsonl` 和 `events.jsonl`。
