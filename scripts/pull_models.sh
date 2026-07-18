#!/usr/bin/env bash
# Pull exactly the models selected by the standard DDT environment variables.

set -euo pipefail

OLLAMA_BIN="${OLLAMA_BIN:-ollama}"
MODELS=(
    "${DDT_OCR_MODEL:-glm-ocr:latest}"
    "${DDT_STRUCT_MODEL:-qwen3.5:4b}"
    "${DDT_VISION_MODEL:-qwen3.5:4b}"
)

if ! command -v "$OLLAMA_BIN" >/dev/null 2>&1; then
    echo "Ollama executable not found: $OLLAMA_BIN" >&2
    exit 1
fi

pulled=" "
for model in "${MODELS[@]}"; do
    if [[ "$pulled" == *" $model "* ]]; then
        continue
    fi
    echo "Pulling $model"
    "$OLLAMA_BIN" pull "$model"
    pulled+="$model "
done

echo "Required Ollama models are available."
