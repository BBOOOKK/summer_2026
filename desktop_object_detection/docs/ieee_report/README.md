# 标准 A4 单栏实验报告

- 主文件：`main.tex`
- 参考文献：`references.bib`
- 图表生成脚本：`scripts/generate_publication_figures.py`
- 最终 PDF：`output/pdf/desktop_object_detection_experiment_report.pdf`
- Jetson 实机结果视频：[jetson_live_detection_20260905_193850.mp4](../../outputs/videos/jetson_live_detection_20260905_193850.mp4)

从项目虚拟环境重建论文图表：

```bash
python scripts/generate_publication_figures.py
```

图表脚本需要 Pillow 和 ReportLab；应使用与当前机器架构一致且已安装这两个包的 Python 环境。

从本目录编译：

```bash
latexmk -xelatex -interaction=nonstopmode -halt-on-error main.tex
```

清理中间文件：

```bash
latexmk -c
```

报告使用 `ctexart` A4 单栏格式和 XeLaTeX 中文字体支持。图表脚本直接读取仓库内的数据集、训练记录与测试结果，并校验测试集混淆矩阵源文件。图6使用 `figures/jetson_recording_32frame_contact_sheet.jpg`，由实机屏幕录像的32个代表性时刻组成；原始录像元数据、抽帧时间和哈希记录在 `../JETSON_MEASUREMENT.md`。`figures/jetson_live_detection.jpg` 保留为从 Jetson 检测流直接取得的单帧记录。实验数字取自正式训练、测试、20 样本结果、Jetson benchmark 和 ROS2 topic 测量。
