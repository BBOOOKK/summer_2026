# 实验一：目标检测与识别实验

> 历史模板，仅保留作格式参考，不代表当前数据或实测结果。正式提交稿位于 `docs/ieee_report/`。

## 1 实验名称

实验一：目标检测与识别实验

## 2 实验目的

使用轻量级 YOLO 对不少于两类桌面物体进行实时检测，在 NVIDIA Jetson 上运行，并通过 ROS2 发布结构化检测结果和带框图像。

## 3 实验环境

| 项目 | 配置 |
| --- | --- |
| Jetson 型号 | 待填写 |
| 操作系统 | 待填写 |
| JetPack | 待填写 |
| CUDA | 待填写 |
| Python | 待填写 |
| PyTorch | 待填写 |
| ROS2 | 待填写 |
| Ultralytics YOLO | 待填写 |

## 4 数据集

检测类别：mouse、keyboard、laptop、cup、headphones。标注格式为 YOLO TXT。

| 项目 | 数量 |
| --- | ---: |
| 总图片 | 500 |
| 训练集 | 347 |
| 验证集 | 100 |
| 测试集 | 53 |
| 负样本 | 50 |
| 总标注框 | 841 |

数据来源与人工审核说明：待根据 `data/provenance.json` 和 `data/QUALITY_REPORT.md` 如实填写。

## 5 模型选择

选择 YOLO11n（兼容性受限时使用 YOLOv8n），原因是参数量小、实时性好、适合 Jetson，并能在精度和速度之间取得合理平衡。

## 6 模型训练

| 参数 | 值 |
| --- | --- |
| epochs | 100 |
| batch size | 16（按显存调整） |
| image size | 640 |
| optimizer | Ultralytics auto |
| learning rate | Ultralytics auto，实际值见 results.csv |
| device | 待填写 |

插入训练损失、PR 曲线、混淆矩阵：`outputs/training/<run>/`。

## 7 检测结果

插入同时包含不少于两类目标、检测框、类别和置信度的典型截图。

| 图片 | 场景 | 结果说明 |
| --- | --- | --- |
| 待插入 | 待填写 | 待填写 |

## 8 模型性能

| Precision | Recall | mAP50 | mAP50-95 |
| ---: | ---: | ---: | ---: |
| 待填写 | 待填写 | 待填写 | 待填写 |

数据来源：`outputs/evaluation/evaluation_results.csv`。

## 9 20 个目标正确率测试

| 测试数量 | 正确数量 | 错误数量 | 正确率 | 要求 | 验收结果 |
| ---: | ---: | ---: | ---: | ---: | --- |
| 20 | 待填写 | 待填写 | 待填写 | ≥ 80% | PASS/FAIL |

## 10 Jetson 实时性能

| 模型 | 推理后端 | 输入尺寸 | 平均 FPS | 最低 FPS | 要求 | 验收结果 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 待填写 | PyTorch/ONNX/TensorRT | 640 | 待填写 | 待填写 | ≥ 5 | PASS/FAIL |

数据来源：`outputs/benchmark/benchmark.csv`。

## 11 ROS2 通信

- 节点：`object_detector`
- 结果 topic：`/object_detection/result`
- 图像 topic：`/object_detection/image`
- 消息：JSON String + sensor_msgs/Image

插入 `ros2 topic echo`、`ros2 topic hz` 和带框图像截图。

## 12 错误案例分析

结合 `outputs/errors/error_cases.csv` 分析：误分类、漏检、遮挡、光照、背景干扰、低置信度和明显误检。每类至少选一个代表性案例，说明原因与改进方向。

## 13 四项关键验收

| 验收项 | 要求 | 实测 | 结果 |
| --- | ---: | ---: | --- |
| A. 同时识别类别 | ≥ 2 类 | 待填写 | PASS/FAIL |
| B. 20 目标正确率 | ≥ 80% | 待填写 | PASS/FAIL |
| C. Jetson 平均 FPS | ≥ 5 | 待填写 | PASS/FAIL |
| D. ROS2 实时发布 | 正常 | 待填写 | PASS/FAIL |

## 14 实验总结

总结模型精度、实时性、ROS2 集成结果、主要错误来源和后续改进方向。明确区分已实测结果与待验证项。
