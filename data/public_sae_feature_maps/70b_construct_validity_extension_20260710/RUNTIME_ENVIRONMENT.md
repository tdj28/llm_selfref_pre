# Runtime Environment

Captured from the live pod after mapping and before termination. No secrets are
included.

## RunPod

- Pod ID: `1anl95txhukear`
- Pod name: `codex-public-sae-powered-n20-20260709`
- Created: `2026-07-09T23:42:54.978Z`
- GPU: NVIDIA A100-SXM4-80GB (81,920 MiB)
- NVIDIA driver: `580.126.16`
- Advertised pod rate: `$1.49/hour`
- OS/kernel: Linux `6.17.0-14-generic`, x86_64
- Mapping completed: `2026-07-10T04:07:04Z`
- Retrieval: all 11 remote raw/map files matched their local SHA-256 hashes.
- Final status: terminated; authenticated GET returned HTTP 404 at
  `2026-07-10T04:11:42Z`.

## Python Runtime

- Python: `3.10.12`
- PyTorch: `2.1.0+cu118`
- CUDA runtime: `11.8`
- Transformers: `4.47.1`
- Accelerate: `0.34.2`
- BitsAndBytes: `0.43.3`
- nnsight: `0.3.0`
- NumPy: `1.24.1`
- huggingface_hub: `0.27.1`
- Model loading: 4-bit quantization

## Pinned Hugging Face Revisions

- Model `meta-llama/Llama-3.3-70B-Instruct`:
  `6f6073b423013f6a7d4d9f39144961bfbfbc386b`
- SAE `Goodfire/Llama-3.3-70B-Instruct-SAE-l50`:
  `128ee921ecd1b8b3a87d776cbcc357c0855da134`

## Executed Mapping Source

```text
87d20789680b84e2dd058a9dad693fa3827da37a32f4807d85f3f62dd83aa2a3  experiments/exp2_sae/map_public_sae_features.py
```

The frozen input JSONL SHA-256 was
`5bdbab2ceffe7385cd942f9c39a0bab0aa235f0f9d4ff3988970ed53d88c92b3`.
The run manifest records the exact command and confirms 2,606 input items.
