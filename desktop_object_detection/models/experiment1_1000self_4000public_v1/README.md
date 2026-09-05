# YOLO11n experiment1_1000self_4000public_v1

- Training data: 1,000 self-collected-source images plus 4,000 Open Images V7 images.
- Self-source disclosure: 10 real source photographs represented by 10 normalized bases and 990 deterministic augmentations; not 1,000 independent shutter events. Some parent photographs depict closely related desktop arrangements.
- Training: 12 epochs, image size 640, batch 32, Apple M4 MPS, initialized from `models/expanded_v1/best.pt`.
- Best validation epoch: 12; Precision 0.7407, Recall 0.7512, mAP50 0.7334, mAP50-95 0.4621.
- Fixed 650-image development holdout: mean per-class Precision 0.8385 and Recall 0.7697, mAP50 0.8386, mAP50-95 0.5735. Its public images retain their historical splits and had already been evaluated in the predecessor experiment.
- Deterministic 20-image Open Images test subset: 20/20, 100%, PASS. This class-balanced subset is part of the 650-image test split, not an additional independent test set.
- Local reproducible video benchmark: 60.409 FPS average on Apple M4 MPS. This is not Jetson evidence.

Use `best.pt` for deployment. `last.pt` is retained for training continuity.

The current fine-tuning dataset contains no generated images. The initialization
checkpoint was trained on the historical mixed dataset, which included 453
generated baseline images; that supervision is part of the final weight history.
The earlier baseline and expanded runs are recorded in
`outputs/training/yolo11n_p05/` and
`outputs/training/yolo11n_p05_expanded_v1_run4/`.

- Acceptance checkpoint SHA-256: `c53834aa239974163ef48c566dc3fea04d38de7a1d05292ab5216d5163a09a42`.
- Initialization checkpoint SHA-256: `8c9ad192ec37128ad10751bf8d7f58a3ee821c4ae0e47733fe0a8d199212c9df`.
