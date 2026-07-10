# Runtime Environment

Captured from the live pod before termination. No secrets are included.

## RunPod

- Pod ID: `6et3y1ogmcxitx`
- Pod name: `codex-public-sae-two-turn-sxm-20260709`
- GPU: NVIDIA A100-SXM4-80GB (81,920 MiB)
- NVIDIA driver: `580.159.04`
- Advertised pod rate: `$1.49/hour`
- OS/kernel: Linux `6.8.0-124-generic`, x86_64, glibc 2.35

## Python Runtime

- Python: `3.10.12` (GCC 11.4.0)
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

## Executed Source Hashes

```text
2783c892f6a0baae1f2eb8fe74332da47385be97adcf2aa12cfdc3c84efe2dfc  experiments/exp2_sae/run_public_sae_placebo_steering.py
c20fe4a424e670a93733b863eb8a5039330c31bcadd7e8d616b33b1d7f6415af  experiments/exp2_sae/replicate_exp2_goodfire_sae.py
8d038b55fa2c3e8098db79d479c210f2c328e01f18a8992082c96a08aeb5bc8f  experiments/exp2_sae/public_sae_protocol.py
```

These hashes match the corresponding local source files at artifact retrieval.
