# Repeated-Answer Funding Amendment A1

This changes one operational choice: the remaining-cost forecast uses a 10%
reserve instead of 30%. The owner authorized this reasonable adaptation within
the existing $130 incremental cap. It adds no funding and changes no models,
prompts, source blocks, answer draws, judges, settings, endpoints or analysis.
The separate $45 Kolibri judging holdback stays intact.

The original scientific freeze is
`b3ddbdcae9919937ffb67da565b26ec2d0c81f00`. Fixtures and the first 48 answers,
including their judges, cost $7.23903055. The initial admission failed because
the $133.8692901 forecast with 30% reserve exceeded both the $122.76096945
remaining study cap and $115.783095403 funded balance after the holdback.
The point forecast is $102.976377; with 10% reserve it is $113.2740147.
This is a cost-based adaptation after initial collection, not a new prospective
scientific design or a guarantee that the full panel will fit.

The failed `admission.json` remains unchanged. Its exact bytes are copied into
the amendment as `FAILED_ADMISSION.json`. The initial journal prefix is
3,101,711 bytes and 274 calls, SHA-256
`6bb8363be09f31b3b71d42c152cc8788f484948352c35e8fb5f5767b85e2887c`.
The wrapper reconstructs that admission from a disposable prefix copy. Labels
and response content do not select the reserve, inventory or budget.

Before bulk collection, freeze and push the separate amendment plan, this
wrapper, its tests, this document and the failed admission anchor. The source
closure includes all 41 original scientific sources, unchanged. Both freezes
are verified. The original `runtime.json`, ledger binding and request metadata
retain the original science freeze so cached requests remain valid. The actual
additional runtime freeze is recorded separately in `funding_a1/runtime.json`
and in each launch's start/finish records, binding the before/after journal.
No claim is made that the funding wrapper ran under the old freeze.

The same locked ledger reserves every call against the $130 cap. Funding is
refreshed before bulk collection and at least every 60 seconds when reserving
new calls. Pending or unresolved charges stay reserved and are not counted as
already debited from the live balance. A refresh may tighten the funded limit,
never expand the cap. Balance-read failures stop new dispatch; running calls
settle normally. Unknown calls are not resent. The $45 holdback is reserved for
the other authorized study, not used to rescue this panel. Other spending
outside that reservation still requires coordination by the parent.

From the repeated-study worktree, build offline:

```sh
python -m experiments.repeat_funding_a1 --build
```

After committing and pushing the amendment plan at
`data/repeated_swap/funding_a1_20261005/PLAN.json`, verify locally with
`--freeze FULL_NEW_SHA`. Parent-only execution adds `--execute` and optionally
`--env-file`. The default performs no provider or inference calls. Do not use
the old main-admission entry point for this continuation, overwrite the failed
admission, change the scientific plan, or create a replacement ledger.

The release adapter must carry both admissions and both runtime identities.
Until that adapter is ready, the original release builder's rejection of the
failed admission must not be bypassed or relabeled as an original pass.
