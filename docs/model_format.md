# Exported model contract

This loop deliberately supports the same on-device backend as `lstm_esp32_uart_pipeline`.

The ESP32-S3 firmware expects two files in SPIFFS (partition label `model`).

`model_fp32.bin`

A packed float32 blob encoding a 1-layer LSTM (hidden size `hidden`) and a linear readout to horizon `H`.
The packing order must match the exporter you already use in `train_lstm_torch_onnx.py`.

`model_meta.json`

A small JSON with at least:

- `T` input window length
- `F` number of input features
- `H` forecast horizon
- `hidden` hidden size

The PC daemon validates `input.npy` against these values and uses them to compute a deterministic parameter count:

`params = 4*hidden*(F + hidden + 1) + H*(hidden + 1)`

If you later add more backends (e.g., TFLM), keep the same outer contract and add `backend` plus backend-specific files.
