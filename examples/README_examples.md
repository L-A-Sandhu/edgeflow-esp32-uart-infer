Examples

1) Create a dummy input from model_meta.json

  python3 scripts/make_dummy_input.py --meta model_meta.json --out X_test.npy --n 8

2) Run one inference request

  ./scripts/infer_curl.sh http://localhost:8080/v2/infer model_fp32.bin model_meta.json X_test.npy infer_out.json
