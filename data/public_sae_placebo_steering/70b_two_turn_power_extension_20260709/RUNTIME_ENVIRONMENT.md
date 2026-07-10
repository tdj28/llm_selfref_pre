# Runtime Environment

Captured from the live pod after generation and before pod termination. No
secrets are included.

## RunPod

- Pod ID: `1anl95txhukear`
- Pod name: `codex-public-sae-powered-n20-20260709`
- GPU: NVIDIA A100-SXM4-80GB (81,920 MiB)
- NVIDIA driver: `580.126.16`
- Advertised pod rate: `$1.49/hour`
- OS/kernel: Linux `6.17.0-14-generic`, x86_64
- Artifact retrieval: every remote file hash matched the local copy.
- Final pod status: terminated after the already-frozen branched-specificity
  and construct-validity follow-ups were retrieved and hash-matched. An
  authenticated pod GET returned HTTP 404 at `2026-07-10T04:11:42Z`.

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

## Executed Source Hashes

```text
8efe1c9128c865cd5ead1060f3c4a6168fae9d5dd6c1f84eb93ba92121701fa0  experiments/exp2_sae/run_public_sae_placebo_steering.py
c20fe4a424e670a93733b863eb8a5039330c31bcadd7e8d616b33b1d7f6415af  experiments/exp2_sae/replicate_exp2_goodfire_sae.py
8d038b55fa2c3e8098db79d479c210f2c328e01f18a8992082c96a08aeb5bc8f  experiments/exp2_sae/public_sae_protocol.py
```

These are the generation-time remote bytes. The release retains them even
though later analysis/audit code is versioned at newer commits.

## Attention-Mask Warning

Transformers 4.47.1 warned that an attention mask could not be inferred because
the pad and EOS IDs are equal. Every request was a batch-size-one, unpadded
sequence. The installed Transformers source returns an all-ones default mask
in exactly this case, so prompt positions were not dropped. The later branched
specificity follow-up passes the same all-ones mask explicitly and records that
mode in turn telemetry.
