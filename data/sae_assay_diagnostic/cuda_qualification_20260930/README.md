# Cheap CUDA Qualification

Source freeze: `711a0c8e6650e57b75e4d2a6ad76a0c5d4fab9c5`.
Plan SHA-256: `ecdc136c5a7601467c9e2e583136427cee6327f255dd31e06d7db788f2d02f8e`.

The newly created RTX 4090 pod passed all 19 tiny-Llama checks and the NF4
linear-layer smoke. The checks exercise known-answer steering arithmetic,
native BF16 encoding, identity controls, cached token replay and hook cleanup.
They took 5.02 seconds after environment startup; total pod lifetime was
approximately 3.2 minutes. No pretrained 70B inference occurred on this pod.

Raw outputs were retrieved and hash-verified before termination. Pod
`qgpy4gtpswy460` was deleted with HTTP 204, followed by direct GET 404 and
inventory absence. Its cost upper bound was $0.0448711851. With the initial
bootstrap failure, all cheap qualification compute/storage cost
$0.0748869338; with the prior Pro call, total spending before the main pod was
$0.9394969338. The original $200 budget remains unchanged.

This is a passed implementation check, not evidence of semantic specificity,
effective target suppression in 70B, or subjective experience. The main run
must pass separate audited real-model gates before bulk collection.
