# IEEE 双栏实验报告

- 主文件：`main.tex`
- 参考文献：`references.bib`
- 最终 PDF：`output/pdf/desktop_object_detection_ieee_report.pdf`

从本目录编译：

```bash
latexmk -xelatex -interaction=nonstopmode -halt-on-error main.tex
```

清理中间文件：

```bash
latexmk -c
```

论文使用 IEEEtran conference 双栏格式和 XeLaTeX 中文字体支持。实验数字取自仓库内正式训练、测试、20 样本结果和 benchmark 输出。
