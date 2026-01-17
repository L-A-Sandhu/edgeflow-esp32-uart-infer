#!/usr/bin/env bash
set -euo pipefail

HOST="${HOST:-http://localhost:8080}"
X_NPY="${1:-X_test.npy}"
MODEL_BIN="${MODEL_BIN:-}"
MODEL_META="${MODEL_META:-}"
OUT="${OUT:-infer_out.json}"

ARGS=( -sS -X POST "${HOST}/v2/infer" -F "input_npy=@${X_NPY}" )

if [[ -n "${MODEL_BIN}" ]]; then
  ARGS+=( -F "model_bin=@${MODEL_BIN}" )
fi
if [[ -n "${MODEL_META}" ]]; then
  ARGS+=( -F "model_meta=@${MODEL_META}" )
fi

curl "${ARGS[@]}" -o "${OUT}"
echo "Wrote ${OUT}"
