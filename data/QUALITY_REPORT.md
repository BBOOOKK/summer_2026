# P05 质量审计报告

结论：`PASS_WITH_PROVENANCE_LIMITATIONS`。数量、命名、YOLO 结构及 S01–S05 核心配额通过；来源中含生成图和公开图，不得宣称为 500 张全实拍。

## 结构结果

- 原图/检查图/标签：500/500/500。
- 来源：{'generated_image': 453, 'local_capture': 10, 'open_images_v7': 37}。
- 模糊度启发式复核项：30；极端曝光复核项：1；可疑框复核项：0。
- dHash 近重复候选对：0（仅作人工复核线索）。
- 启发式告警已作模型辅助联系表复核：模糊度 30 张、曝光 1 张，未发现目标不可识别图。

## 已验证的语义要求

- S01 五类各 25 张：True；角度距离平衡：True。
- S02 组合配额不匹配项：0。
- S02 角度距离平衡：True；九格联系表复核：True。
- S03 角度距离平衡：True；背景光照 20 格各 5 张：True。
- S04 角度距离平衡：True；四类挑战各 25 张：True。
- S05 负样本 10/20/20 配额：True；全部空标签：True。

## 未通过或无法证明的要求

- S02 adjacent accepted images change at least two capture factors is based on contact-sheet review rather than complete per-factor metadata。
- all target instances exhaustively annotated in Open Images-sourced photos。
- independent second human review has not been performed; visual review in this package is model-assisted。

## 建议验收口径

当前包可按混合来源数据集验收；启发式模糊/曝光告警是人工复核线索，不等于自动判废。
