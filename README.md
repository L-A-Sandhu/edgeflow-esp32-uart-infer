# EdgeFlow V2

EdgeFlow V2 provides an HTTP inference API for an ESP32-S3 running on-device neural inference over UART. The host side runs as a Dockerized FastAPI service and bridges HTTP requests to a framed UART protocol. You can hot-swap the deployed model by flashing only a dedicated SPIFFS partition while keeping the firmware unchanged.

Keywords
ESP32-S3 edge AI, microcontroller inference, UART inference server, ESP-IDF SPIFFS model partition, FastAPI Docker gateway, time series forecasting on ESP32.

## What you get

- HTTP API for inference on an ESP32-S3 
- UART framing that tolerates boot logs and misalignment 
- Optional model update in the same request by flashing only the model partition 
- Deterministic input contract via model_meta.json 
- Docker image based on the official Espressif ESP-IDF container

## Repository layout

- esp32/model_client  ESP-IDF project that serves inference over UART and loads model files from the SPIFFS partition named model
- pc                  FastAPI server, UART protocol, and model flashing utilities
- docker              Container entrypoint and docker compose
- docs                Model file contract

## Architecture

Your client sends a multipart HTTP request that includes an input tensor and optionally a new model. The gateway validates input shapes, flashes the model partition if requested, and then streams each sample to the ESP32-S3 over UART.

Client  curl or Python
  -> FastAPI gateway inside Docker
    -> UART protocol INFO META INFR PRED
      -> ESP32-S3 firmware loads model from SPIFFS partition model

Takeaway
This repo separates model lifecycle management from firmware builds.

## Requirements

Host
- Linux recommended because Docker can pass through /dev/ttyACM0 directly
- Docker and Docker Compose
- Permission to access the serial device. On many systems you need to be in the dialout group

Device
- ESP32-S3 board with USB serial
- ESP-IDF is only required if you want to build flash outside Docker. Docker already includes ESP-IDF

Takeaway
You can run the full stack with only Docker plus an ESP32-S3.

## Quickstart

### Step 1  Flash the ESP32 firmware once

Option A  Flash from your host

Install ESP-IDF on your host. Then run firmware commands through this repo's wrapper, which sources ESP-IDF only for the duration of the command (no permanent shell changes).

Build and flash

```bash
# From repo root
IDF_PATH=$HOME/esp-idf make fw-flash ESP_PORT=/dev/ttyACM0 ESP_BAUD=460800

# Or without Makefile
IDF_PATH=$HOME/esp-idf ./scripts/idf -C esp32/model_client set-target esp32s3
IDF_PATH=$HOME/esp-idf ./scripts/idf -C esp32/model_client -p /dev/ttyACM0 -b 460800 build flash
```

Option B  Flash from the container

Set FLASH_FIRMWARE=1 in docker docker-compose.yml environment and start the container. This uses idf.py flash.

Takeaway
After firmware flash the board is stable and only the model partition changes.

### Step 2  Start the gateway

```bash
cd docker
docker compose up --build
```

The service listens on http://localhost:8080.

Health check

```bash
curl -sS http://localhost:8080/health | jq
```

Takeaway
The gateway owns the UART link and serializes requests.

### Step 3  Run inference

Create a valid input tensor

```bash
python3 scripts/make_dummy_input.py --T 32 --F 4 --n 8 --out X_test.npy
```

Send inference

```bash
curl -sS -X POST http://localhost:8080/v2/infer \
  -F "input_npy=@X_test.npy" \
  -o infer_out.json
cat infer_out.json | jq
```

Takeaway
You get JSON predictions plus timing and device metadata.

## Hot swap the model

You can upload a new model in the same request. The gateway writes the files into esp32/model_client/spiffs_image and runs idf.py model-flash. The ESP32 reboots and then serves inference with the new parameters.

```bash
curl -sS -X POST http://localhost:8080/v2/infer \
  -F "model_bin=@model_fp32.bin" \
  -F "model_meta=@model_meta.json" \
  -F "input_npy=@X_test.npy" \
  -o infer_out.json
```

Takeaway
This implements model updates without rebuilding or reflashing firmware.

## API

GET /health returns readiness plus device info.

GET /v2/info returns device dimensions.

POST /v2/infer returns JSON with pred plus timing.

POST /v2/infer_npy returns a .npy payload with pred.

## Model contract

The firmware loads two files from the SPIFFS partition labeled model.

- model_fp32.bin  packed float32 weights for the on-device backend
- model_meta.json keys T F H hidden

See docs/model_format.md for the exact contract and parameter count.

Takeaway
The gateway enforces (N,T,F) compatibility before streaming bytes over UART.

## Run without Docker

If you prefer a local venv

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SERIAL_PORT=/dev/ttyACM0
uvicorn pc.server:app --host 0.0.0.0 --port 8080
```

Takeaway
Docker is the default because it bundles ESP-IDF for model flashing.

## Troubleshooting

Serial permission denied

```bash
sudo usermod -a -G dialout $USER
```
Log out and back in.

Wrong serial port

Set SERIAL_PORT in docker/docker-compose.yml or export SERIAL_PORT when running locally.

Model flash fails

- Ensure the container can run privileged and see /dev/ttyACM0
- Ensure the ESP32 firmware build exists. The entrypoint compiles once on first start

Shape mismatch

The device reports T and F over UART and the gateway rejects any input that does not match.

Takeaway
Most failures are port permissions, board reset windows, or (T,F) mismatches.

## Citation

If you use EdgeFlow in academic work, cite the GitHub repository and describe the contract in docs/model_format.md.
