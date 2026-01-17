"""UART protocol compatible with the ESP32-S3 model_client firmware.

This module intentionally mirrors the proven protocol used by hw_compare_uart.py:

Host -> Device
  MAGIC_META (b'META')
      Request model metadata.

  MAGIC_INFR (b'INFR') + uint32(nfloats) + float32 payload
      Send one sample (flattened) for inference.

Device -> Host
  MAGIC_INFO (b'INFO') + uint32(T) + uint32(F) + uint32(H) + uint32(hidden)
      Report model dimensions.

  MAGIC_PRED (b'PRED') + uint32(H) + float32[H]
      Return one prediction vector.

The serial stream can include unrelated boot logs. The reader therefore scans
for magic sequences rather than assuming alignment.
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass


MAGIC_META = b"META"
MAGIC_INFO = b"INFO"
MAGIC_INFR = b"INFR"
MAGIC_PRED = b"PRED"


@dataclass(frozen=True)
class DeviceInfo:
    T: int
    F: int
    H: int
    hidden: int


def _read_exact(ser, n: int, where: str, timeout_s: float) -> bytes:
    """Read exactly n bytes or raise TimeoutError."""
    deadline = time.time() + timeout_s
    out = bytearray()
    while len(out) < n:
        if time.time() > deadline:
            raise TimeoutError(f"serial timeout at {where}: need={n} got={len(out)}")
        chunk = ser.read(n - len(out))
        if chunk:
            out += chunk
    return bytes(out)


def _read_until_magic(ser, magic: bytes, where: str, timeout_s: float) -> None:
    """Scan the stream until the 4-byte magic appears."""
    if len(magic) != 4:
        raise ValueError("magic must be 4 bytes")

    deadline = time.time() + timeout_s
    window = bytearray()
    while True:
        if time.time() > deadline:
            raise TimeoutError(f"serial timeout at {where}: waiting for {magic!r}")
        b = ser.read(1)
        if not b:
            continue
        window += b
        if len(window) > 4:
            window = window[-4:]
        if len(window) == 4 and bytes(window) == magic:
            return


def query_info(ser, timeout_s: float = 10.0) -> DeviceInfo:
    """Request and parse INFO."""
    # request
    ser.write(MAGIC_META)
    ser.flush()

    # response
    _read_until_magic(ser, MAGIC_INFO, "INFO.magic", timeout_s)
    payload = _read_exact(ser, 8, "INFO.payload", timeout_s)
    T, F, H, hidden = struct.unpack("<4H", payload)
    return DeviceInfo(int(T), int(F), int(H), int(hidden))


def infer_one(ser, x_flat_f32: bytes, H: int, timeout_s: float = 10.0) -> bytes:
    """Send one sample (flattened float32 bytes) and receive prediction bytes.

    Firmware response format is:
      MAGIC_PRED + uint32(H_device) + float32[H_device]

    This host validates H_device against expected H to avoid silent framing bugs.

    Returns raw bytes of len H*4 (float32).
    """
    if len(x_flat_f32) % 4 != 0:
        raise ValueError("x_flat_f32 must be float32 bytes")

    nfloats = len(x_flat_f32) // 4
    ser.write(MAGIC_INFR)
    ser.write(struct.pack("<I", nfloats))
    ser.write(x_flat_f32)
    ser.flush()

    _read_until_magic(ser, MAGIC_PRED, "PRED.magic", timeout_s)

    # Firmware sends uint32(H) before payload.
    h_bytes = _read_exact(ser, 4, "PRED.H", timeout_s)
    (H_dev,) = struct.unpack("<I", h_bytes)
    if int(H_dev) != int(H):
        raise ValueError(f"Device reported H={H_dev} but host expects H={H}")

    return _read_exact(ser, H * 4, "PRED.payload", timeout_s)
