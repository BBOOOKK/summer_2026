# YOLO11n experiment1_1000self_4000public_v1

- Training data: 1,000 self-collected-source images plus 4,000 Open Images V7 images.
- Self-source disclosure: 10 independent real captures plus 990 deterministic derived augmentations; not 1,000 independent shutter events.
- Training: 12 epochs, image size 640, batch 32, Apple M4 MPS, initialized from `models/expanded_v1/best.pt`.
- Best validation epoch: 12; Precision 0.7407, Recall 0.7512, mAP50 0.7334, mAP50-95 0.4621.
- Independent 650-image test: Precision 0.8385, Recall 0.7697, mAP50 0.8386, mAP50-95 0.5735.
- Deterministic 20-image Open Images test subset: 20/20, 100%, PASS. This class-balanced subset is part of the 650-image test split, not an additional independent test set.
- Local reproducible video benchmark: 60.409 FPS average on Apple M4 MPS. This is not Jetson evidence.

Use `best.pt` for deployment. `last.pt` is retained for training continuity.
