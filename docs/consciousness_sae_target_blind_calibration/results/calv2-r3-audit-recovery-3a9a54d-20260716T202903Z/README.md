# Calibration v2 final recovery result

The final audit-only recovery completed successfully on the immutable `calv2-r3-1a16572-20260715T002344Z` transaction. The independent offline verifier accepted all 14 retrieved files with no network access and no bundle modification. The exact B200 pod was then deleted with unrelated inventory unchanged.

## Result

The calibration succeeded as a prerequisite for a separately frozen SAE experiment, but it does not itself test an SAE or consciousness.

- All 120 rows passed hard safety. All 96 gated 2%, 3%, 4%, and 8% edits passed delivery; all 24 diagnostic 1% rows failed the fidelity gate and should not be used.
- Source delivery was locally linear in all 24 prompt-by-direction rows over 2/3/4%. Applying J to the realized edit was also locally linear in all 24 rows.
- The actual final model response was nonlinear in all 24 rows. Actual-final cosine ranged from 0.7683 to 0.8763 and slope discrepancy from 0.5112 to 0.7138.
- At the sole confirmatory layer 50, the real J beat the best of five random controls for residual cosine and fixed-token logit Pearson.
- The real J beat identity for logit Pearson, but not for residual cosine. The stronger learned-J-added-value-over-identity claim is therefore not eligible.
- Layers 51–78 remain descriptive only and cannot rescue the layer-50 primary result. No layer passed the full diagnostic learned-J-added-value conjunction.

The correct interpretation is: faithful generic edits enter the model, the linear J calculation scales properly, and substantial nonlinearity appears downstream. This clears later discrete actual-state collection while requiring that J be treated as a bounded descriptive readout rather than demonstrated superior to identity.

This run used zero target SAE feature vectors and zero target or paper prompts. It supports no claim about SAE nonlinearity, deception, self-reference, consciousness, subjective experience, hidden belief, intent, or behavior.

## Storage and provenance

- Network volume: `bv9gb9j32y`
- Raw transaction: `/workspace/consciousness_sae_target_blind_calibration/consciousness_sae_target_blind_calibration_v2/raw/calv2-r3-1a16572-20260715T002344Z`
- Recovery attempt: `/workspace/csae/calv2-r3-audit-recovery-3a9a54d-20260716T202903Z`
- Code/review chain: C15 `af0d8b94921f0fb8809f06aacbf8546fb726cb54`, E15 `386d68d3fc6bf0f89e0d6ee5f6b9fc04529c322a`, F15 `3a9a54dc4ff7ec60265a86e7d340e0b6c0b39749`
- Full compact summary SHA-256: `053d4585cc139f8a0ec9bc93e6eeaaa105cda822b3a6144292d5038328712f93`
- Full compact audit SHA-256: `88e96ecb554aa18acbd838649a49034ae4f532898255cdc27220e25ed662f596`

The large compact audit and summary remain on the network volume and are not committed here. This directory retains the small publication, offline-verification, launch-gate, termination, and interpreted-result indexes.

## Post-retrieval validator incident

The remote controller returned success and published the result, but the local supervisor returned code 100 after retrieval. The gate wrote the two rejected B20/B22 authorization hashes in sorted order; the redundant validator expected the same two members in reverse insertion order. Both validator invocations stopped on that representation mismatch.

An in-memory diagnostic changing only the expected ordering made the complete validator pass, including the retrieved authorization. The independent offline bundle verifier also passed, publication is complete, and termination is clean. The original red validator status remains disclosed; it is not rewritten and the scientific run is not repeated. Future launch chains should test an exact producer-to-consumer receipt round trip instead of comparing these arrays as sets.
