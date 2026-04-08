#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODELS_DIR="$ROOT_DIR/runtime/models"
MODEL_NAME="${1:-ggml-small.bin}"
MODEL_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/${MODEL_NAME}"
TARGET_PATH="$MODELS_DIR/$MODEL_NAME"
TMP_PATH="${TARGET_PATH}.part"

mkdir -p "$MODELS_DIR"

echo "[whisper] Lade Modell herunter: $MODEL_NAME"
echo "[whisper] Quelle: $MODEL_URL"

if [[ -f "$TMP_PATH" ]]; then
  echo "[whisper] Setze unterbrochenen Download fort ..."
fi

curl -L --fail -C - --progress-bar "$MODEL_URL" -o "$TMP_PATH"
mv "$TMP_PATH" "$TARGET_PATH"

echo "[whisper] Modell bereit: $TARGET_PATH"
echo "[whisper] Hinweis: Setze in den Settings whisper_model_path auf diesen Pfad."
