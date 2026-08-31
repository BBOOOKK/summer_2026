#!/bin/zsh
set -e

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"

if [[ -x "../work/p05env/bin/python" ]]; then
  PYTHON_BIN="../work/p05env/bin/python"
elif [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
else
  PYTHON_BIN="python3"
fi

DATASET="datasets/p05_expanded_v1/dataset.yaml"
START_MODEL="models/best.pt"
OUTPUT_MODELS="models/expanded_v1"

if [[ ! -f "$DATASET" ]]; then
  echo "缺少扩充数据集: $DATASET"
  read -k 1 "?按任意键退出..."
  exit 1
fi

if [[ ! -f "$START_MODEL" ]]; then
  START_MODEL="yolo11n.pt"
fi

echo "P05 扩充版微调"
echo "数据: $DATASET (5000 张)"
echo "起始权重: $START_MODEL"
echo "设备: MPS | 图像尺寸: 512 | batch: 16 | epochs: 30"
echo "新权重保存到: $OUTPUT_MODELS（不会覆盖当前 models/best.pt）"

exec "$PYTHON_BIN" scripts/train.py \
  --data "$DATASET" \
  --model "$START_MODEL" \
  --epochs 30 \
  --batch 16 \
  --imgsz 512 \
  --device mps \
  --workers 4 \
  --patience 10 \
  --project outputs/training \
  --name yolo11n_p05_expanded_v1 \
  --models-dir "$OUTPUT_MODELS" \
  "$@"
