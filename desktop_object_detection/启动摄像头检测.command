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

echo "P05 桌面目标实时检测"
echo "摄像头: 0 | 模型: models/expanded_v1/best.pt | 设备: MPS"
echo "按 s 保存截图；按 q 或 ESC 退出。"

exec "$PYTHON_BIN" scripts/detect_camera.py \
  --model models/expanded_v1/best.pt \
  --camera 0 \
  --device mps \
  --imgsz 640 \
  --conf 0.5 \
  --iou 0.45 \
  --show \
  "$@"
