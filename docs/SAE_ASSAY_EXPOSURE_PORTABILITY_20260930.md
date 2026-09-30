# CPU Arithmetic Portability Check

This is a **post-outcome verification amendment**, written after the completed
224-text screen and 48-forward precision pilot. It changes no experimental
data, scientific threshold, sample, coefficient, operator or frozen source.

## Preserved Failure

The frozen pilot validator recomputes CPU FP64 delivery arrays from the retained
BF16/FP32 tensors and compares Python dictionaries for exact equality. It
passes on the Linux worker before the completion receipt. The same validator
on the ARM Mac fails at `Raw delivery reconstruction mismatch` for 40 of 48
rows. Its original source and the local failure record remain unchanged.

Maximum absolute discrepancies across the local Torch recomputation are:

| Quantity | Maximum absolute difference |
|---|---:|
| Requested norm | 4.663e-15 |
| Realized norm | 4.663e-15 |
| Clean norm | 1.137e-13 |
| Cosine | 5.218e-15 |
| Relative error | 1.518e-18 |
| Realized / clean norm | 1.527e-16 |
| Nonzero-request and exact-identity flags | 0 |

The discrepancy occurs in reduction results, not file hashes, raw tensor
values, token IDs or whether `post == pre.float() + request`. It is consistent
with platform-dependent FP64 reduction ordering; this observation does not
identify the exact compiler or kernel responsible.

## Separate Verification

The frozen exact validator remains the record of the original check. A named
portability adapter permits only the CPU delivery-metric equality comparison
to use `rtol=1e-12, atol=1e-12`. Boolean/integer values, hashes, shapes, token
inventories, captures, receipt chains, precision paths, paired baselines and
raw FP32 addition identities retain their original exact checks. Any other
validation error must still fail. The adapter is scoped to explicit offline
verification and reporting; it cannot change the executed worker.

For every position, recompute the original zero/nonzero masks, fidelity
criterion and norm criterion. Classification and denominators must match
exactly, independently of the metric tolerance. Retain the exact-audit error,
all maximum differences and the adapter's source hash in the public evidence.
Do not report the amended check as a pass of the original exact validator.

The separate NumPy verifier, which does not import scientific analysis
functions, finds zero count, denominator or threshold-classification changes
across all 224 clean and 48 pilot rows. It uses its own documented
`rtol=1e-10, atol=1e-12` metric comparison; this does not replace the stricter
adapter's checks. Both signed branches remain 290/290 for fidelity and norm,
with 958 zero requests each. Native-zero/sham denominators remain zero and
their fractions undefined. Feature 22004's inadequate exposure remains a
failure. None of these checks qualifies a behavioral assay.

The post-outcome adapter is an implementation-portability correction, not a
new scientific analysis selected to cross a failed effect threshold. The
original platform passes, exact raw identities, independent reconstruction,
and unchanged per-position decisions are distinct pieces of evidence; all
are retained rather than substituting a generic tolerance for provenance.
