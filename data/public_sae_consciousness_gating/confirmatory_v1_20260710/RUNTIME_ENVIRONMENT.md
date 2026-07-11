# Runtime Environment And Pod Lifecycle

## Generation And Local Judge

- RunPod pod ID: `zniqey1k45alvd`
- Pod name: `codex-sae-gating-calibration-20260710`
- GPU: NVIDIA A100-SXM4-80GB
- Reported rate: `$1.49/hour`
- Created: approximately `2026-07-10T09:28Z`
- Generation completed: `2026-07-11T02:09Z`
- Termination verified: approximately `2026-07-11T02:40Z`
- Termination evidence: REST DELETE returned HTTP 204, direct GET returned HTTP
  404, and the subsequent authenticated account inventory contained zero pods.
- Frozen generation/local-judge commit:
  `d7e1b7984badb2359417ed708bfb4c0429c6dbe9`
- Model cache: `/workspace/huggingface_cache`

The pod was reused for the primary local Llama judge so the pinned model did
not need to be reacquired. Two startup-only failures produced zero judgment
rows and are preserved in `judging/`. The first omitted the separately stored
Hugging Face token from the new process environment. The second used the
default container cache and exhausted the 30 GB overlay while redundantly
downloading shards. Only that duplicate cache was removed. An offline
model/tokenizer preflight then passed against the original workspace cache,
after which the unchanged frozen judge completed all 1,500 rows.

`judging/local_judge_runtime.json`, `local_judge_pip_freeze.txt`, and
`local_judge_gpu.txt` provide the sanitized machine-readable environment. API
keys, Hugging Face tokens, model weights, and cache contents are not included.

## External Judges

The two external judges ran locally from the repository's `steering/.venv`
with six workers. Their packet-locked raw outputs retain provider response IDs,
resolved model names, usage, and completion metadata but no credentials.
`judging/external_judge_runtime.json` records the client environment.
