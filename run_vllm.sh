#!/usr/bin/env bash
set -euo pipefail
# Запуск vLLM (Qwen2.5-VL) отдельным контейнером на машине с NVIDIA GPU.
# После старта приложение (api) обращается к нему по host.docker.internal:8000.

IMAGE="${IMAGE:-vllm/vllm-openai:latest}"
CONTAINER_NAME="${CONTAINER_NAME:-dara-vllm}"
GPU_DEVICE="${GPU_DEVICE:-0}"
HOST_PORT="${HOST_PORT:-8000}"
CONTAINER_PORT="${CONTAINER_PORT:-8000}"

# ВАЖНО: нужна ВИЖН-модель (VL). Текстовый Qwen2.5-7B изображения не примет.
MODEL="${MODEL:-Qwen/Qwen2.5-VL-7B-Instruct}"
# Меньше VRAM: Qwen/Qwen2.5-VL-3B-Instruct (~8-10 ГБ) или *-AWQ (квантованная).
# Локальная модель: MODEL=/root/models/Qwen2.5-VL-7B-Instruct

SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-qwen}"   # = VLM_MODEL в .env приложения
MAX_MODEL_LEN="${MAX_MODEL_LEN:-16384}"          # ~до 5 страниц накладной
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.85}"
MAX_NUM_SEQS="${MAX_NUM_SEQS:-8}"
LIMIT_MM_IMAGES="${LIMIT_MM_IMAGES:-5}"           # картинок на запрос (до 5 страниц)
MAX_PIXELS="${MAX_PIXELS:-1310720}"               # потолок пикселей -> токены на картинку

HF_CACHE_DIR="${HF_CACHE_DIR:-$HOME/.cache/huggingface}"
LOCAL_MODELS_DIR="${LOCAL_MODELS_DIR:-$HOME/models}"
HF_TOKEN="${HF_TOKEN:-}"

echo "=== NVIDIA ==="
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv || true
echo
echo "=== Pull image ==="
docker pull "${IMAGE}"
echo
echo "=== Stop old container if exists ==="
docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true
echo
echo "=== Start vLLM (Qwen2.5-VL) on :${HOST_PORT} ==="
docker run --rm \
  --name "${CONTAINER_NAME}" \
  --gpus "device=${GPU_DEVICE}" \
  --ipc=host \
  -p "${HOST_PORT}:${CONTAINER_PORT}" \
  -v "${HF_CACHE_DIR}:/root/.cache/huggingface" \
  -v "${LOCAL_MODELS_DIR}:/root/models" \
  -e "HF_TOKEN=${HF_TOKEN}" \
  "${IMAGE}" \
  "${MODEL}" \
  --served-model-name "${SERVED_MODEL_NAME}" \
  --host 0.0.0.0 \
  --port "${CONTAINER_PORT}" \
  --max-model-len "${MAX_MODEL_LEN}" \
  --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}" \
  --max-num-seqs "${MAX_NUM_SEQS}" \
  --limit-mm-per-prompt "{\"image\": ${LIMIT_MM_IMAGES}}" \
  --mm-processor-kwargs "{\"max_pixels\": ${MAX_PIXELS}}"

# Когда модель загрузится (GET /health -> 200), запускайте приложение:
#   MOCK_VLM=false docker compose up --build
# api обращается к этому vLLM по http://host.docker.internal:${HOST_PORT}/v1
