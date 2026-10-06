# Repeated-Answer Summary Figure

The main paper uses a four-point summary: two response models and two readers.
Each point is the original complete-request SH-minus-HS estimate, counting
explicit or implicit current claims. Astra's intervals remain 97.5% for nominal
95% coverage across the fixed two-model primary family; Opus's remain descriptive
95%. Missing judgments are not filled in or recoded. Bootstrap coverage is
approximate and conditional on complete requests.

The unchanged block-level and variance plot remains in the pinned archive,
linked from the uncertainty appendix. A compact appendix table retains its
conservative all-planned bounds, including the intervals crossing zero for
Opus responses, are not replaced by the narrower bars in this summary. The
main text and caption continue to disclose that sensitivity result.

This package copies estimates and intervals from the hash-pinned original
publication in `../repeated_extension/`. It performs no new inference. The
original raw-data replay and immutable publication check remain part of
`make paper-verify`.

```sh
python scripts/verify_repeated_presentation.py
python -m unittest tests.test_repeated_presentation tests.test_repeated_editorial tests.test_model_comparison_condensation
```

`--write` rebuilds only this editorial package; `--rerender` compares fresh
PDF and PNG exports with the saved files. The original release and figures
remain unchanged.
