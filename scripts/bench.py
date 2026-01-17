#!/usr/bin/env python3
"""Simple latency benchmark for /v2/infer.

Example
  python3 scripts/bench.py --url http://localhost:8080/v2/infer --input X_test.npy --runs 50
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import requests


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8080/v2/infer")
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--model_bin", type=Path, default=None)
    ap.add_argument("--model_meta", type=Path, default=None)
    ap.add_argument("--runs", type=int, default=20)
    args = ap.parse_args()

    x = args.input.read_bytes()
    files_base = {"input_npy": (args.input.name, x, "application/octet-stream")}

    lat = []
    for i in range(args.runs):
        files = dict(files_base)
        if args.model_bin is not None:
            files["model_bin"] = (args.model_bin.name, args.model_bin.read_bytes(), "application/octet-stream")
        if args.model_meta is not None:
            files["model_meta"] = (args.model_meta.name, args.model_meta.read_bytes(), "application/json")

        t0 = time.time()
        r = requests.post(args.url, files=files, timeout=120)
        dt = (time.time() - t0) * 1000.0
        r.raise_for_status()
        lat.append(dt)

        if i == 0:
            js = r.json()
            print("device", json.dumps(js.get("device", {}), indent=2))

    lat = np.array(lat, dtype=np.float32)
    print(f"runs={args.runs} mean_ms={lat.mean():.2f} p50_ms={np.percentile(lat,50):.2f} p95_ms={np.percentile(lat,95):.2f}")


if __name__ == "__main__":
    main()
