# B200 execution smoke

Run this once after the provider, guest, and public-artifact preflights and
after issuance of the machine-produced pre-execution authorization, but before
the full Stage A grid. It is an operational check, not a pilot or a scientific
result. The authorization must bind this exact plan/source/review, the live
pushed Git commit, the provider chain, and the same campaign deadline.

The smoke uses `neutral_smoke01`, a mundane prompt absent from both frozen
prompt panels. It loads the exact pinned model, SAE, and J-lens through the same
`V2Backend` used by Stage A/B, then performs exactly four model forwards:

1. one prefix-cache forward;
2. one clean final-token arc;
3. one positive 0.25%-RMS generic edit at layer 50; and
4. its exact negative pair.

It requires complete layer 45--78 captures for all three arcs, one hook fire
per edited branch, byte-exact native BF16 addition, unchanged upstream layers
45--49, one real-J layer-50 transport, and a 64-token selected-logit panel. A
deterministic top-8/bottom-8 replay checks that the selected-logit readout is
byte-repeatable. This is deliberately not a full-vocabulary replay claim.

The command is:

```bash
python3 -B -u -m experiments.consciousness_sae_realization_validation.guest_launcher \
  --ownership-receipt "$OWNERSHIP_RECEIPT" smoke -- \
  --plan-dir "$PLAN_DIR" \
  --volume-root /workspace \
  --volume-id "$VOLUME_ID" \
  --run-id "$SMOKE_RUN_ID" \
  --model-snapshot "$CACHE_ROOT/model_snapshot" \
  --sae-path "$CACHE_ROOT/sae/Llama-3.3-70B-Instruct-SAE-l50.pt" \
  --j-lens-path "$CACHE_ROOT/jlens/Llama-3.3-70B-Instruct_jacobian_lens.pt" \
  --hourly-price-usd "$HOURLY_PRICE_USD" \
  --campaign-started-at-unix "$CAMPAIGN_STARTED_AT_UNIX" \
  --provider-terminate-at-unix "$PROVIDER_TERMINATE_AT_UNIX" \
  --preexecution-authorization "$PREEXECUTION_AUTHORIZATION" \
  --guest-receipt "$GUEST_RECEIPT" \
  --cache-receipt "$CACHE_RECEIPT"
```

Do not invoke `smoke_test` directly. The bound launcher validates the
provider-derived container-image attestation in `OWNERSHIP.json`, refuses a
conflicting pre-existing image or CUDA setting, sets
`CUBLAS_WORKSPACE_CONFIG=:4096:8`, binds the ownership self-hash, and only then
executes a fresh Python process. The backend revalidates all three bindings
before importing Transformers or touching Torch/model state.

The self-hashed receipt is written outside the raw namespace at:

```text
/workspace/consciousness_sae_realization_validation/
  consciousness_sae_realization_validation_v1/
  operational_smoke_receipts/<run-id>.json
```

The smoke validates the authorization before loading the backend. Its receipt
binds the authorization self-hash, ownership/guest/cache hashes, plan/source
hashes, campaign identity and deadline, and its exact external relative path.
Stage A accepts only that exact single-link external file and records both its
receipt self-hash and physical file SHA-256.

The receipt fixes all target and paper-prompt counts at zero and declares
itself ineligible for scientific gates and dose selection. Neither its metrics
nor its top-k rows may be copied into Stage A/B inputs, used to revise a dose,
or reported as evidence about SAE/J-lens fidelity. A failed smoke blocks launch
for infrastructure debugging. A passing smoke satisfies one operational
prerequisite; it is not itself execution authority and cannot replace the
pre-execution authorization.
