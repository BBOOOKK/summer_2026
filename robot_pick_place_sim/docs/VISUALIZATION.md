# 仿真可视化

正式验收提供三类互相校验的可视化：

1. `fortress_final_demo_20260905.mp4`：Gazebo Fortress 相机传感器录制的厂家 mechArm 270 CAD 抓放成片；
2. `fortress_final_demo_preview.png`：成片中搬运至 B 区的关键帧；
3. `fortress_acceptance_dashboard.svg`：5 次落点、B 区容差、耗时、抬升高度和禁碰结果。

最终成片不是关节数据重画，也没有根据关节状态推测目标物是否被抓住。视频图像直接来自
`/demo_camera/image`；厂家 CAD、目标物和桌面均由 Fortress 渲染。顶部状态和底部进度条是录制器叠加层。
成片运行 `20260905_103122_24fadc` 同时记录了左右指接触、物体轨迹、0 次禁碰和最终落点；详见同名 JSON 清单。

重新录制 Gazebo 场景：

```bash
python3 scripts/record_fortress_demo.py \
  --output acceptance_logs/fortress_camera.mp4 --fps 10 --timeout 180
```

可视化只负责呈现；最终合格判断仍由 `acceptance_summary.json` 的自动证据门禁给出。
