#!/usr/bin/env python3
from __future__ import annotations

import os
import time
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import serial
from dataclasses import asdict

from .protocol import query_info, infer_one, DeviceInfo


def _run(cmd: list[str], timeout_s: int) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_s,
            env=os.environ.copy(),
        )
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        raise TimeoutError(f"timeout running: {' '.join(cmd)} after {timeout_s}s") from e


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


class DeviceManager:
    def __init__(
        self,
        serial_port: str = "/dev/ttyACM0",
        uart_baud: int = 115200,
        idf_baud: int = 921600,
        esp_project: Optional[Path] = None,
        probe_timeout_s: float = 6.0,
    ) -> None:
        self.serial_port = serial_port
        self.uart_baud = int(uart_baud)
        self.idf_baud = int(idf_baud)
        self.probe_timeout_s = float(probe_timeout_s)

        self.esp_project = esp_project or (Path(__file__).resolve().parents[1] / "esp32" / "model_client")
        self.spiffs_dir = self.esp_project / "spiffs_image"

        # Critical: must be re-entrant because flash_model() may call probe_info()
        self._lock = threading.RLock()

    def ensure_built(self) -> None:
        build_ninja = self.esp_project / "build" / "build.ninja"
        if not build_ninja.exists():
            self._idf("build", timeout_s=1800)

    def _idf(self, *args: str, timeout_s: int = 900) -> Dict[str, Any]:
        cmd = ["idf.py", "-C", str(self.esp_project), "-p", self.serial_port, "-b", str(self.idf_baud), *args]
        t0 = time.time()
        rc, out, err = _run(cmd, timeout_s=timeout_s)
        dt = time.time() - t0
        if rc != 0:
            raise RuntimeError(
                "idf.py failed\n"
                f"cmd: {' '.join(cmd)}\n"
                f"rc: {rc}\n"
                f"stdout:\n{out}\n"
                f"stderr:\n{err}\n"
            )
        return {"cmd": cmd, "seconds": dt, "stdout": out, "stderr": err}

    def _probe_info_nolock(self) -> DeviceInfo:
        with serial.Serial(self.serial_port, self.uart_baud, timeout=0.1) as ser:
            try:
                ser.reset_input_buffer()
                ser.reset_output_buffer()
            except Exception:
                pass
            return query_info(ser, timeout_s=self.probe_timeout_s)

    def probe_info(self) -> DeviceInfo:
        with self._lock:
            return self._probe_info_nolock()

    def flash_model(self, model_bin: bytes, model_meta: Optional[bytes] = None) -> Dict[str, Any]:
        with self._lock:
            self.ensure_built()
            self.spiffs_dir.mkdir(parents=True, exist_ok=True)
            _atomic_write_bytes(self.spiffs_dir / "model_fp32.bin", model_bin)
            if model_meta is not None:
                _atomic_write_bytes(self.spiffs_dir / "model_meta.json", model_meta)

            flash_res = self._idf("model-flash", timeout_s=600)

            # device reboot window
            time.sleep(1.5)

            # IMPORTANT: do not re-enter lock inside probe_info()
            info = self._probe_info_nolock()
            return {"model_flash": flash_res, "device_info": asdict(info)}

    def infer(self, x: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
        if not isinstance(x, np.ndarray):
            raise TypeError("x must be a numpy array")
        if x.dtype != np.float32:
            x = x.astype(np.float32, copy=False)

        if x.ndim == 2:
            x = x[None, ...]
        if x.ndim != 3:
            raise ValueError(f"input must have shape (T,F) or (N,T,F), got {x.shape}")

        with self._lock:
            t0 = time.time()
            with serial.Serial(self.serial_port, self.uart_baud, timeout=0.1) as ser:
                try:
                    ser.reset_input_buffer()
                    ser.reset_output_buffer()
                except Exception:
                    pass

                info = query_info(ser, timeout_s=self.probe_timeout_s)
                T, F, H = int(info.T), int(info.F), int(info.H)

                if x.shape[1] != T or x.shape[2] != F:
                    raise ValueError(f"shape mismatch: got {x.shape}, device expects (N,{T},{F})")

                preds = np.zeros((x.shape[0], H), dtype=np.float32)
                per_sample_ms = []

                for i in range(x.shape[0]):
                    payload = np.ascontiguousarray(x[i].reshape(-1)).tobytes()
                    ts = time.time()
                    y_bytes = infer_one(ser, payload, H, timeout_s=10.0)
                    per_sample_ms.append((time.time() - ts) * 1000.0)
                    preds[i] = np.frombuffer(y_bytes, dtype=np.float32, count=H)

            total_ms = (time.time() - t0) * 1000.0
            return preds, {
                "device_info": asdict(info),
                "n_samples": int(x.shape[0]),
                "total_ms": total_ms,
                "per_sample_ms": per_sample_ms,
                "mean_per_sample_ms": float(np.mean(per_sample_ms)) if per_sample_ms else 0.0,
            }
