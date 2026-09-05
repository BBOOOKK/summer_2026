# A4 Single-Column Experiment Report

This directory contains the reproducible English report for Experiment 1.

- LaTeX source: `main.tex`
- Bibliography: `references.bib`
- Figure-generation script: `scripts/generate_publication_figures.py`
- Final PDF: `output/pdf/desktop_object_detection_experiment_report.pdf`
- Jetson result video: `../../outputs/videos/jetson_live_detection_20260905_193850.mp4`

Regenerate the evidence-based figures from the repository data:

```bash
python scripts/generate_publication_figures.py
```

The figure script requires Pillow and ReportLab. Use a Python environment whose
packages match the host architecture.

Compile the report from this directory with XeLaTeX:

```bash
latexmk -xelatex -interaction=nonstopmode -halt-on-error main.tex
```

Remove intermediate LaTeX files when required:

```bash
latexmk -c
```

The document uses the standard `article` class in A4 single-column format. Its
figures are generated from the repository's dataset manifests, training logs,
test results, and verified confusion-matrix source. Figure 6 is the 32-frame
sequence in `figures/jetson_recording_32frame_contact_sheet.jpg`, sampled from
the continuous Jetson screen recording; extraction times and file hashes are
recorded in `../JETSON_MEASUREMENT.md`. The original single-frame capture is
retained as `figures/jetson_live_detection.jpg`.

Reported values come from the selected training run, the 650-image test split,
the current-weight 20-image assessment, the Jetson benchmark, and the measured
ROS 2 topic frequency. The report explicitly separates independent source
captures from augmented derivatives and separates model-call throughput from
ROS 2 publication rate.
