# 当前验收权重的多类别定性结果

本目录保存报告图 5 的可复核输出。该结果用于说明模型能够在同一帧内同时定位并分类不少于两类物体，不替代 650 张 test 集的总体检测指标，也不作为 Jetson 性能数据。

## 输入与来源

- 输入：`datasets/experiment1_1000self_4000public_v1/images/test/self_IMG_8306_v000.jpg`
- 数据划分：当前 5000 张数据集的 `test`
- 来源记录：`self_collected_derived`，原始拍摄文件 `IMG_8306.JPG`
- 版本：`v000`，仅执行尺寸统一；旋转、缩放、平移、翻转、亮度、对比度、模糊和噪声参数均为恒等值
- 真值类别：`laptop`、`keyboard`、`mouse`

来源字段可在 `datasets/experiment1_1000self_4000public_v1/manifest.csv` 和 `self_collected_provenance.json` 中复核。

## 模型与参数

- 权重：`models/experiment1_1000self_4000public_v1/best.pt`
- 权重 SHA-256：`c53834aa239974163ef48c566dc3fea04d38de7a1d05292ab5216d5163a09a42`
- 环境：Python 3.12.4、PyTorch 2.13.0、Ultralytics 8.4.133、OpenCV 5.0.0
- 后端：Apple MPS
- 参数：`imgsz=640`、`confidence=0.50`、`NMS IoU=0.45`

## 输出

| 类别 | 置信度 |
| --- | ---: |
| laptop | 0.923283 |
| keyboard | 0.918365 |
| mouse | 0.863124 |

- 标注图：`current_test_self_real_imgsz640_conf050_iou045/self_IMG_8306_v000_20260905_204222.jpg`
- 逐框记录：`current_test_self_real_imgsz640_conf050_iou045/self_IMG_8306_v000_20260905_204222.csv`
- 标注图 SHA-256：`504d8139614cecd3ad799cd0a708102dbae347d402a7585e7a7a03a1c70e27ed`
- CSV SHA-256：`afbc0cd3f514a6b4a9bf8030f52758af7eb53b42e60b083b1772bb745f71e967`

## 复现命令

```bash
python scripts/detect_image.py \
  --model models/experiment1_1000self_4000public_v1/best.pt \
  --source datasets/experiment1_1000self_4000public_v1/images/test/self_IMG_8306_v000.jpg \
  --imgsz 640 --conf 0.50 --iou 0.45 --device mps \
  --output outputs/evaluation/current_model_demo/current_test_self_real_imgsz640_conf050_iou045
```
