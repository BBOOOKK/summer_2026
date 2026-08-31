# Experiment 1 dataset: 1,000 self-collected-source + 4,000 public

This dataset contains exactly 5,000 YOLO-format images for five classes: `mouse`, `keyboard`, `laptop`, `cup`, and `headphones`.

## Composition

- 1,000 `self_collected_derived` images: 10 original photos captured by the dataset owner, each represented by 100 deterministic variants.
- 4,000 `open_images_v7` images: selected from the existing Open Images V7 import while preserving its official split boundary.
- Split totals: train 4,000, validation 350, test 650.

The 1,000-image self-collected-source count is an owner-authorized project rule. It consists of 10 independent camera captures and 990 derived augmentations, not 1,000 independent shutter events. This distinction must remain visible in any report or acceptance presentation.

The 10 original captures cover mouse, keyboard, and laptop. Cup and headphones are represented by public images.

## Leakage control and provenance

Original self-captured photos are assigned by source group: 8 sources to train, 1 to validation, and 1 to test. All variants from an original stay in the same split. `self_collected_provenance.json` records the original filename, SHA256 digest, split, variant number, and transform parameters for every derived image. `manifest.csv` records the source type and source ID for all 5,000 images.

## Verification

- `build_report.json`: exact count and broken-link check.
- `qa/provenance_audit.json`: 1,000 + 4,000 provenance target check.
- `qa/dataset_check_report.json`: YOLO label and class-range validation.
- `qa/expanded_quality_report.json`: image decode, duplicate, source-group leakage, box, and contact-sheet audit.
- `qa/self_derived_contact_sheet.jpg`: labeled sample of real-photo-derived images.

Public bounding boxes are converted from Open Images annotations and have engineering QA, but they have not all been manually re-labeled. Formal ground-truth claims should preserve that limitation.
