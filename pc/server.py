#!/usr/bin/env python3
"""
EdgeFlow V2 HTTP server.

The server exposes a single container-friendly API:
- POST /v2/infer      -> JSON response (predictions as lists)
- POST /v2/infer_npy  -> application/octet-stream (.npy with pred)
- GET  /v2/info       -> current device model dimensions
- GET  /health        -> readiness probe

Request format (multipart/form-data)
- model_bin   optional file  model_fp32.bin
- model_meta  optional file  model_meta.json
- input_npy   required file  input.npy  (float32 array of shape (N,T,F) or (T,F))
"""
from __future__ import annotations

import io
import os
import json
import time
from typing import Optional, Any, Dict
from dataclasses import asdict, is_dataclass

import numpy as np
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, Response

from .device_manager import DeviceManager

APP_PORT = int(os.getenv("PORT", "8080"))
SERIAL_PORT = os.getenv("SERIAL_PORT", "/dev/ttyACM0")
UART_BAUD = int(os.getenv("UART_BAUD", "115200"))
IDF_BAUD = int(os.getenv("IDF_BAUD", "921600"))

app = FastAPI(title="EdgeFlow V2", version="2.0.0")
mgr = DeviceManager(serial_port=SERIAL_PORT, uart_baud=UART_BAUD, idf_baud=IDF_BAUD)


def _load_npy(upload_bytes: bytes) -> np.ndarray:
    try:
        arr = np.load(io.BytesIO(upload_bytes), allow_pickle=False)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"failed to read .npy: {e}")
    if not isinstance(arr, np.ndarray):
        raise HTTPException(status_code=400, detail="uploaded .npy did not decode into an ndarray")
    if arr.dtype != np.float32:
        arr = arr.astype(np.float32, copy=False)
    return arr


@app.get("/health")
def health() -> Dict[str, Any]:
    info = mgr.probe_info()
    device = asdict(info) if is_dataclass(info) else (info if isinstance(info, dict) else dict(getattr(info, '__dict__', {})))
    return {"ok": True, "device": device, "port": SERIAL_PORT}
@app.get("/v2/info")
def v2_info() -> Dict[str, Any]:
    info = mgr.probe_info()
    device = asdict(info) if is_dataclass(info) else (info if isinstance(info, dict) else dict(getattr(info, '__dict__', {})))
    return {"ok": True, "device": device, "port": SERIAL_PORT, "model": "v2"}
@app.post("/v2/infer")
async def v2_infer(
    input_npy: UploadFile = File(...),
    model_bin: Optional[UploadFile] = File(None),
    model_meta: Optional[UploadFile] = File(None),
) -> JSONResponse:
    t0 = time.time()

    x = _load_npy(await input_npy.read())

    flash_timing = None
    if model_bin is not None:
        mb = await model_bin.read()
        mm = await model_meta.read() if model_meta is not None else None
        flash_timing = mgr.flash_model(mb, mm)

    pred, timing = mgr.infer(x)

    total_ms = (time.time() - t0) * 1000.0
    out = {
        "ok": True,
        "device": timing["device_info"],
        "timing_ms": {
            "flash": flash_timing["model_flash"]["seconds"] * 1000.0 if flash_timing else 0.0,
            "total": total_ms,
            "mean_per_sample": timing["mean_per_sample_ms"],
        },
        "pred": pred.tolist(),
    }
    return JSONResponse(out)


@app.post("/v2/infer_npy")
async def v2_infer_npy(
    input_npy: UploadFile = File(...),
    model_bin: Optional[UploadFile] = File(None),
    model_meta: Optional[UploadFile] = File(None),
) -> Response:
    x = _load_npy(await input_npy.read())

    if model_bin is not None:
        mb = await model_bin.read()
        mm = await model_meta.read() if model_meta is not None else None
        mgr.flash_model(mb, mm)

    pred, _timing = mgr.infer(x)

    buf = io.BytesIO()
    np.save(buf, pred, allow_pickle=False)
    return Response(content=buf.getvalue(), media_type="application/octet-stream")
