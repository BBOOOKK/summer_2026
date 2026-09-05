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

Reported values come from the selected training run, the 650-image development holdout,
the current-weight 20-image assessment, the Jetson benchmark, and the measured
ROS 2 topic frequency. The report explicitly separates independent source
captures from augmented derivatives and separates model-call throughput from
ROS 2 publication rate.

The report includes experimental questions, source-stratified box counts,
checkpoint lineage, an acceptance-evidence matrix, retrospective confidence
filtering, inspected error cases, a discussion, and a conclusion. It retains
the 32-frame Jetson sequence as Figure 6. Review examples below confidence 0.60
are identified separately from actual box-level failures.

The current 5,000-image dataset contains no generated images; the historical
initialization checkpoint includes mixed-source training. The public holdout
was already used for evaluation in that earlier experiment, and self-derived
holdout samples share a source photograph. Neither the 650-image results nor
the 20-image subset is described as an external blind test.

Regenerate the public-source stratum of the development holdout from the project
root:

```bash
python scripts/evaluate_public_holdout.py --device mps --batch 4 \
  --output outputs/evaluation/public_holdout_reproduction
```

The script freezes cohort membership from the manifest before validation. The
cohort contains 550 Open Images V7 photographs and 807 provider boxes already
present in the reused 650-image development holdout. It obtained macro precision
0.7927, macro recall 0.7114, mAP@0.5 0.7762, and mAP@0.5:0.95 0.5593. This is a
source-stratified analysis, not a new independent test set. Frozen results and
per-image provenance are stored in
`outputs/evaluation/experiment1_1000self_4000public_v1_public_holdout/`.
The `.absolute.yaml` and `.absolute.txt` files there preserve the original
measurement machine's paths as historical run records; a reproduction creates a
new output directory and writes absolute paths for the current machine.

Regenerate the three inspected error cases from the project root:

```bash
python scripts/save_report_error_cases.py --device mps \
  --output outputs/errors/holdout_error_reproduction
```

The command uses the identified acceptance checkpoint, confidence 0.50, NMS IoU
0.45, and one image per prediction call. Frozen outputs used by the report are stored in
`outputs/errors/experiment1_1000self_4000public_v1_holdout/` with source IDs,
hashes, boxes, and IoU records. These purposeful examples are separate from the
fixed 20-image class-decision result and are not used to estimate an error rate.

Frozen input identifiers (SHA-256):

- Current manifest: `59eaa679c3cb301e805afb51df5e14aceb02572530d5c72713d1c15ec82a7dda`.
- Repository dataset configuration: `0b7ab4c5fb5ac4a59b90cab473e3c5d4277253e48384b3a91b03272e2f189d77`.
- Repository 20-image selection: `4138ead379b69b6363a987910cf10c29be38c8898c5cb2b6f48c58ade0c19aee`.
- Fine-tuning arguments: `23f40eccd8ae36d46c9a9fc77ff5ed069f970136ae927af2e6a3d5f72b30881f`.

Paths in the self-contained submission archive are adjusted for portability;
its own `SHA256SUMS.txt` identifies the packaged versions.
