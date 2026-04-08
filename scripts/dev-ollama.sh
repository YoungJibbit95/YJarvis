#!/usr/bin/env bash
set -euo pipefail

OLLAMA_HOST="${JARVIS_OLLAMA_HOST:-127.0.0.1}"
OLLAMA_PORT="${JARVIS_OLLAMA_PORT:-11434}"
OLLAMA_HEALTH_URL="http://${OLLAMA_HOST}:${OLLAMA_PORT}/api/tags"

if ! command -v ollama >/dev/null 2>&1; then
  echo "[ollama] Binary nicht gefunden. Bitte installieren: brew install ollama"
  exit 1
fi

if curl -sf --max-time 2 "$OLLAMA_HEALTH_URL" >/dev/null 2>&1; then
  echo "[ollama] Bereits aktiv unter ${OLLAMA_HOST}:${OLLAMA_PORT} (externer Prozess)."
  echo "[ollama] Dev-Runner bleibt aktiv, bis du den Dev-Stack stoppst."
  trap 'exit 0' INT TERM
  while true; do
    sleep 3600
  done
else
  echo "[ollama] Starte lokalen Ollama-Server auf ${OLLAMA_HOST}:${OLLAMA_PORT} ..."
  exec ollama serve
fi
