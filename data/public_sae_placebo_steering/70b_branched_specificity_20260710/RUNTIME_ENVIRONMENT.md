# Runtime Environment

Captured from the live pod after generation and before termination. No secrets
are included.

## RunPod

- Pod ID: `1anl95txhukear`
- Pod name: `codex-public-sae-powered-n20-20260709`
- Created: `2026-07-09T23:42:54.978Z`
- GPU: NVIDIA A100-SXM4-80GB (81,920 MiB)
- NVIDIA driver: `580.126.16`
- Advertised pod rate: `$1.49/hour`
- OS/kernel: Linux `6.17.0-14-generic`, x86_64
- Generation completed: `2026-07-10T03:43:01Z`
- Retrieval: all eight remote generation files matched local SHA-256 hashes.
- Final status: terminated after the subsequent frozen mapping job; an
  authenticated GET returned HTTP 404 at `2026-07-10T04:11:42Z`.

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

## Executed Generation Source Hashes

```text
8bf97a44ec70afb9248bb11af99b22ab8435827954ddf1a74ea8e3a540b3227d  experiments/exp2_sae/run_public_sae_branched_specificity.py
8efe1c9128c865cd5ead1060f3c4a6168fae9d5dd6c1f84eb93ba92121701fa0  experiments/exp2_sae/run_public_sae_placebo_steering.py
8d038b55fa2c3e8098db79d479c210f2c328e01f18a8992082c96a08aeb5bc8f  experiments/exp2_sae/public_sae_protocol.py
12b15863bf53cb9906260bec576ba9bab1eae0dc225f09031d80425438d7f378  experiments/exp2_sae/replicate_exp2_goodfire_sae.py
```

These are the generation-time remote bytes identified in
`specificity_manifest.json`. Later judge, analysis, and independent-audit code
is versioned separately in git.
