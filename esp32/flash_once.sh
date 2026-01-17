#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-/dev/ttyACM0}"
BAUD_FLASH="${BAUD_FLASH:-460800}"

PROJ_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/model_client"

cd "$PROJ_DIR"

# you must have sourced:  . /home/lasandhu/esp-idf/export.sh
idf.py set-target esp32s3
idf.py -p "$PORT" -b "$BAUD_FLASH" build flash

echo "\nFlashed. Exit monitor (Ctrl+]) if you run it, then start the PC daemon."
