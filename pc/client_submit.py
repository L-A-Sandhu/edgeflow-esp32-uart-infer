#!/usr/bin/env python3
"""
Optional local client for EdgeFlow V2.

Example
python3 pc/client_submit.py --host http://127.0.0.1:8080 \
  --model model_fp32.bin --meta model_meta.json --input input.npy --out pred.npy
"""
from __future__ import annotations
import argparse
import sys
import pathlib
import requests

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="http://127.0.0.1:8080")
    ap.add_argument("--input", required=True, help="input.npy (float32, shape (N,T,F) or (T,F))")
    ap.add_argument("--model", default=None, help="optional model_fp32.bin")
    ap.add_argument("--meta", default=None, help="optional model_meta.json")
    ap.add_argument("--out", default="pred.npy", help="output pred.npy")
    ap.add_argument("--json", action="store_true", help="use /v2/infer JSON endpoint instead of /v2/infer_npy")
    args = ap.parse_args()

    files = {"input_npy": open(args.input, "rb")}
    if args.model:
        files["model_bin"] = open(args.model, "rb")
    if args.meta:
        files["model_meta"] = open(args.meta, "rb")

    try:
        if args.json:
            r = requests.post(args.host.rstrip("/") + "/v2/infer", files=files, timeout=600)
            r.raise_for_status()
            print(r.json())
        else:
            r = requests.post(args.host.rstrip("/") + "/v2/infer_npy", files=files, timeout=600)
            r.raise_for_status()
            pathlib.Path(args.out).write_bytes(r.content)
            print(f"wrote {args.out}")
    finally:
        for f in files.values():
            try: f.close()
            except Exception: pass
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
