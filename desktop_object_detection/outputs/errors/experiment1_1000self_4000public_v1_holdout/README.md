# Purposefully selected test-set error cases

This directory contains three qualitative cases selected from the public
portion of the existing 650-image test split. The folder name is retained for
the report workflow; these images are not an independent statistical holdout.
They were selected purposefully after aggregate evaluation and must not be
used to estimate an overall error rate.

The evidence is generated with the frozen acceptance checkpoint at image size
640, confidence threshold 0.50, NMS IoU threshold 0.45, and device mps. Each
source image is sent through a separate model.predict call. No retraining or
parameter update is performed, and the saved cases do not alter the frozen
650-image AP results.

## Recorded outcomes

| Source ID | Purposeful case type | Predictions at confidence 0.50 | IoU 0.50 interpretation |
| --- | --- | --- | --- |
| 6eb03384f25d3f01 | Missed headphones | No accepted prediction | One false negative |
| 0378fe468292e979 | Localization mismatch | headphones 0.714034 | Same-class IoU 0.468169; one localization false positive and one false negative |
| 34da803c6cae973c | Spurious cup prediction | cup 0.846040; headphones 0.610839 | cup is a wrong-class false positive; headphones is a true positive with IoU 0.768871 |

The third source contains headphones and no visible cup. Its cup prediction is
therefore a false positive both relative to the provider annotation and under
direct visual inspection.

Acceptance checkpoint SHA-256:
c53834aa239974163ef48c566dc3fea04d38de7a1d05292ab5216d5163a09a42

Files:

- error_case_evidence.json: complete provenance, hashes, versions,
  configuration, GT boxes, predictions, IoU records, and case-level notes.
- case_summary.csv: one machine-readable row per selected case.
- boxes.csv: one row for every provider GT and predicted box.
- pairwise_iou.csv: every prediction-to-GT IoU pair.
- 01_headphones_missed_gt_vs_prediction.jpg: provider GT beside the
  no-detection result.
- 02_headphones_localization_gt_vs_prediction.jpg: correct class with an
  IoU below 0.50.
- 03_spurious_cup_gt_vs_prediction.jpg: headphones prediction accompanied by
  a spurious cup prediction; no cup is visible in the source image.

The side-by-side images duplicate the source pixels into GT and prediction
panels and add only headings, boxes, labels, and a legend. They do not replace
or modify the dataset source files.
