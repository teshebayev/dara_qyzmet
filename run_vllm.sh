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
# По умолчанию — AWQ (квантованная): влезает в ~16 ГБ VRAM. Полный fp16-вес
# (Qwen/Qwen2.5-VL-7B-Instruct) требует ~16.5 ГБ и на 16 ГБ падает с CUDA OOM.
MODEL="${MODEL:-Qwen/Qwen2.5-VL-7B-Instruct-AWQ}"
# Ещё меньше VRAM: Qwen/Qwen2.5-VL-3B-Instruct-AWQ.
# Локальная модель: MODEL=/root/models/Qwen2.5-VL-7B-Instruct-AWQ

SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-qwen}"   # = VLM_MODEL в .env приложения
MAX_MODEL_LEN="${MAX_MODEL_LEN:-8192}"           # запас по памяти; ~до 3 страниц накладной
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.85}"
MAX_NUM_SEQS="${MAX_NUM_SEQS:-8}"
LIMIT_MM_IMAGES="${LIMIT_MM_IMAGES:-5}"           # картинок на запрос (до 5 страниц)
MAX_PIXELS="${MAX_PIXELS:-1310720}"               # потолок пикселей -> токены на картинку
# Tool-calling для агента (function-calling). Для Qwen2.5 — парсер hermes.
TOOL_CALL_PARSER="${TOOL_CALL_PARSER:-hermes}"

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
  --mm-processor-kwargs "{\"max_pixels\": ${MAX_PIXELS}}" \
  --enable-auto-tool-choice \
  --tool-call-parser "${TOOL_CALL_PARSER}"

# Когда модель загрузится (GET /health -> 200), запускайте приложение:
#   docker compose up --build
# api обращается к этому vLLM по http://host.docker.internal:${HOST_PORT}/v1
