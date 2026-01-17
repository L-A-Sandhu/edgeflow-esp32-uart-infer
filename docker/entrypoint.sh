#!/usr/bin/env bash
set -euo pipefail

SERIAL_PORT="${SERIAL_PORT:-/dev/ttyACM0}"
UART_BAUD="${UART_BAUD:-115200}"
IDF_BAUD="${IDF_BAUD:-921600}"
PORT="${PORT:-8080}"

# ESP project path inside the container
ESP_PROJECT="${ESP_PROJECT:-/workspace/esp32/model_client}"

# Activate ESP-IDF environment (idf.py + managed Python venv)
source /opt/esp/idf/export.sh >/dev/null 2>&1

# Optional one-time compile (no flashing). Needed to generate build artifacts used by model partition flashing.
if [[ ! -f "${ESP_PROJECT}/build/build.ninja" ]]; then
  echo "[edgeflow-v2] First start: idf.py build (compile only) ..."
  idf.py -C "${ESP_PROJECT}" build
  echo "[edgeflow-v2] Build complete."
fi

# Optional firmware flash (off by default)
if [[ "${FLASH_FIRMWARE:-0}" == "1" ]]; then
  echo "[edgeflow-v2] FLASH_FIRMWARE=1 -> flashing firmware ..."
  idf.py -C "${ESP_PROJECT}" -p "${SERIAL_PORT}" -b "${IDF_BAUD}" flash
  echo "[edgeflow-v2] Firmware flash done."
fi

# Optional default model flash (off by default; set 1 if you keep a default spiffs_image)
if [[ "${FLASH_SPIFFS_DEFAULT:-0}" == "1" ]]; then
  # If the project defines a custom target, this will work. Otherwise it will just no-op or fail.
  echo "[edgeflow-v2] FLASH_SPIFFS_DEFAULT=1 -> flashing default model partition (if available) ..."
  set +e
  idf.py -C "${ESP_PROJECT}" -p "${SERIAL_PORT}" -b "${IDF_BAUD}" model-flash
  set -e
fi

export SERIAL_PORT UART_BAUD IDF_BAUD ESP_PROJECT

exec python -m uvicorn pc.server:app --host 0.0.0.0 --port "${PORT}"
