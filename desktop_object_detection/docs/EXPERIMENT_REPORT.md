# 实验一：目标检测与识别实验报告

> 本文件为项目内的 Markdown 摘要，不作为正式提交稿。标准 A4 单栏 LaTeX 报告及最终 PDF 位于 `docs/ieee_report/`。

## 1 实验目的

使用轻量级 YOLO 检测五类桌面目标，在 NVIDIA Jetson 上实现实时识别，并通过 ROS2 发布类别、检测框、置信度和带框图像。验收重点为同时识别不少于两类、20 个样本正确率不低于 80%、Jetson 平均 FPS 不低于 5，以及 ROS2 实时发布。

## 2 实验环境

开发与训练环境为 macOS、Apple M4、Python 3.12.4、PyTorch 2.13.0、Ultralytics 8.4.133 和 MPS。边缘端采用 NVIDIA Jetson Orin NX Engineering Reference Developer Kit Super（16 GB）、JetPack 6.2.1、L4T 36.4.4、CUDA runtime 12.6.77、NVIDIA build PyTorch 2.5.0 和 ROS2 Humble。实机推理后端为 PyTorch FP16；系统虽安装 TensorRT 10.7.0.23 运行库，本次测量未使用 TensorRT Engine。

## 3 数据集

数据集包含 mouse、keyboard、laptop、cup、headphones 五类，YOLO 水平框标注。确定性分层划分如下：

| 集合 | 图片 | 标签 | 空标签 | 目标框 |
| --- | ---: | ---: | ---: | ---: |
| train | 4,000 | 4,000 | 0 | 6,773 |
| val | 350 | 350 | 0 | 627 |
| test | 650 | 650 | 0 | 1,107 |
| 合计 | 5,000 | 5,000 | 0 | 8,507 |

各类框数为 mouse 1,724、keyboard 1,966、laptop 2,549、cup 1,397、headphones 871。

来源必须如实披露：1,000 张自主采集来源素材由 10 张独立实拍照片和 990 张确定性增强图组成；另有 4,000 张 Open Images V7 公开图片。该计数口径由数据集所有者确认，但不能表述为 1,000 次独立拍摄。10 个实拍母图按 8/1/1 分组，所有衍生版本只进入同一划分，避免母图跨 train/val/test 泄漏。旧 P05 基线中的生成图不进入当前验收版。

## 4 模型与训练

模型采用 YOLO11n，原因是网络轻量、6.4 GFLOPs，适合 Jetson 的实时场景。训练输入 640，batch 32，AdamW 自动优化器，使用有限旋转、平移、缩放、水平翻转和 Mosaic，禁用 MixUp。

从历史扩充模型继续迁移学习，共完成 12 个 epoch，最佳 checkpoint 来自第 12 个 epoch。最终提供：

- `models/experiment1_1000self_4000public_v1/best.pt`
- `models/experiment1_1000self_4000public_v1/last.pt`
- 训练曲线、PR 曲线、混淆矩阵：`outputs/training/experiment1_1000self_4000public_v1/`

## 5 独立测试集结果

| Precision | Recall | mAP50 | mAP50-95 |
| ---: | ---: | ---: | ---: |
| 0.8385 | 0.7697 | 0.8386 | 0.5735 |

| 类别 | Precision | Recall | mAP50 | mAP50-95 |
| --- | ---: | ---: | ---: | ---: |
| mouse | 0.933 | 0.910 | 0.950 | 0.755 |
| keyboard | 0.835 | 0.847 | 0.901 | 0.636 |
| laptop | 0.912 | 0.753 | 0.864 | 0.460 |
| cup | 0.909 | 0.741 | 0.857 | 0.675 |
| headphones | 0.604 | 0.598 | 0.620 | 0.342 |

详细 CSV：`outputs/evaluation/experiment1_1000self_4000public_v1_test/evaluation_results.csv`。

## 6 多类别同时识别

在当前 5000 张数据集的 test 划分中，选取自主采集来源基准图 `self_IMG_8306_v000.jpg`，以当前验收权重、置信度阈值 0.5 和 NMS IoU 阈值 0.45 推理，同一帧内正确检出 laptop、keyboard 和 mouse 三类，满足“不少于两类”要求。标注图与逐框 CSV 保存于 `outputs/evaluation/current_model_demo/current_test_self_real_imgsz640_conf050_iou045/`。

## 7 20 个目标正确率

测试集从独立 test 划分中每类选取 4 张单目标图，共 20 张；最高置信度类别作为最终预测。

| 测试数量 | 正确 | 错误 | 正确率 | 要求 | 结果 |
| ---: | ---: | ---: | ---: | ---: | --- |
| 20 | 19 | 1 | 95.00% | ≥ 80% | PASS |

唯一错误为 laptop 漏检。相关文件为 `outputs/evaluation/experiment1_1000self_4000public_v1_test/20_object_test_results.csv` 和 `outputs/errors/experiment1_1000self_4000public_v1/error_cases.csv`。

## 8 实时性能

本机 MPS 使用 640 输入、130 个计时帧的平均预测调用速率为 60.409 FPS，最低 34.733 FPS，该结果仅用于训练机软件检查。

Jetson 在 `MAXN_SUPER` 动态调频模式下使用当前 `best.pt`、CUDA device 0 和 FP16。预热 20 帧后统计 200 帧，完整 `model.predict()` 调用平均耗时为 25.951 ms，对应 38.534 FPS；最低预测调用速率为 37.952 FPS。Ultralytics 报告的平均网络推理耗时为 20.575 ms，最大为 20.896 ms。上述预测调用计时不包含摄像头读取、绘框、写盘或 ROS2 发布，平均速度超过 5 FPS 验收阈值。

## 9 ROS2 通信

节点 `object_detector` 支持 USB 摄像头和 `/camera/image_raw` 两种输入；发布：

- `/object_detection/result`：`std_msgs/msg/String` JSON。
- `/object_detection/image`：`sensor_msgs/msg/Image` 带框图像。

ROS2 Humble 节点在 Jetson 上运行，`/object_detection/result` 经 15 s、200 条消息滑动窗口测得 29.99 Hz。该数值表示结果消息到达订阅端的实际频率，与节点 JSON 中按预测调用耗时计算的平滑 FPS 分开记录。

## 10 结果视频与错误分析

Jetson 实机检测流已保存为 30 秒、900 帧、$640\times480$ 的 H.264 视频 `outputs/videos/jetson_live_detection_20260905_193850.mp4`，画面包含类别、检测框、置信度和预测调用速率。20 样本测试中的唯一错误为 laptop 漏检；该样本及相应记录已单独保存。视频的 30 帧/s 是封装回放时基，不作为模型或 ROS2 性能测量值。

## 11 四项验收结论

| 验收项 | 要求 | 当前结果 | 状态 |
| --- | ---: | ---: | --- |
| A. 同时识别类别 | ≥ 2 类 | 5 类 | PASS |
| B. 20 目标正确率 | ≥ 80% | 95.00% | PASS |
| C. Jetson 平均 FPS | ≥ 5 | 38.534 FPS | PASS |
| D. ROS2 实时发布 | 正常 | 结果主题 29.99 Hz | PASS |

## 12 总结

本实验完成了数据构建、YOLO11n 训练、独立测试、20 样本统计、错误案例保存、Jetson 摄像头推理和 ROS2 结果发布。当前验收模型以 PyTorch FP16 权重运行；测试集检测、20 样本类别判定、Jetson 实时性能及 ROS2 发布频率均达到课程验收阈值。正式论述、图表和参考文献以 `docs/ieee_report/` 中的 LaTeX 报告为准。
