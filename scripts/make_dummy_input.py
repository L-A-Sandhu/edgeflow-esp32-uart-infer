#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

def read_TF(meta: Path) -> tuple[int, int]:
    obj = json.loads(meta.read_text(encoding='utf-8'))
    if 'T' not in obj or 'F' not in obj:
        raise SystemExit('model_meta.json must contain keys T and F')
    return int(obj['T']), int(obj['F'])

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--meta", type=Path, default=None, help="path to model_meta.json")
    p.add_argument("--T", type=int, default=None)
    p.add_argument("--F", type=int, default=None)
    p.add_argument("--n", type=int, default=1, help="number of samples N")
    p.add_argument("--out", type=Path, required=True, help="output .npy")
    args = p.parse_args()


    if args.meta is not None:
        T, F = read_TF(args.meta)
    else:
        if args.T is None or args.F is None:
            raise SystemExit("Provide --meta or both --T and --F")
        T, F = int(args.T), int(args.F)

    N = int(args.n)
    x = np.random.randn(N, T, F).astype(np.float32)
    if N == 1:
        x = x[0]  # (T,F)
    np.save(args.out, x, allow_pickle=False)
    print(f"Wrote {args.out} with shape {x.shape} dtype {x.dtype}")

if __name__ == "__main__":
    main()
