# Assay Release Format Correction

CI identified two packaging problems after the calibration release. Neither
changes the frozen GPU runtime, scientific plan, raw rows, hashes or verdicts.

1. The CPU verification environment did not install Transformers, which the
   new offline tiny-Llama tests import. `requirements-ci.txt` now includes the
   same pinned Transformers, tokenizer, Hub and safetensors versions used by
   the assay. The tests are retained, not skipped or weakened.
2. The bootstrap-failure and successful CUDA-qualification manifests used a
   filename-to-hash mapping. Their hashes were checked locally, but the
   repository's public-release validator requires a list of path/size/hash
   records. Each exact original manifest is retained as
   `MANIFEST.original.json`; `MANIFEST.json` is converted to the established
   format and additionally binds the original manifest.

The format correction is explicit because these files were already public.
The original bootstrap failure, successful qualification, termination receipts
and every raw byte remain preserved. The separate immutable calibration
snapshot manifest is not changed.
