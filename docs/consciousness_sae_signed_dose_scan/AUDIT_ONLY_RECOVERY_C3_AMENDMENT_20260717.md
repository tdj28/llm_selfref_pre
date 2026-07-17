# Audit-only recovery C3 amendment — 2026-07-17

The user explicitly authorized C3 after disclosure of the consumed C2
qualification failure: “Authorize C3 and augment the experiment skill with
lesson learned”. This amendment creates a fresh cycle; it is not a retry and
does not retroactively pass C2 or amend the scientific design.

`RECOVERY_CYCLE_LEDGER_V3.json` freezes global qualification ordinal 3,
successor attempt 1, protocol and namespace version v3, and permanent rejection
of pods `wl8obvtuq0ax8t`, `69d9kxugxuf6up`, and `g2azyjkpm17f1s`. The
qualification pod must be new; the recovery pod must be new and distinct from
it. No old authority, run ID, namespace, or output may be reused.

C3 permits exactly one 1,800-second / $3 target-host qualification; after a
pass, exactly one compact top-level Pro review capped at $1.25; after every gate
passes, exactly one zero-forward audit-only recovery capped at 3,600 seconds /
$6. The hard deadline is `2026-07-17T18:00:00Z`. There are zero automatic,
provider-capacity, qualification, review, or recovery retries. Any red gate or
failure consumes its attempt, preserves compact evidence, terminates the exact
owned pod, and stops for new human authority.

Qualification and review have no raw-run argument and may open no raw or
outcome artifact. Recovery may open only the immutable original raw transaction
after passing qualification and review; it may not load or call a model or
alter raw bytes. Raw data remains on the network volume and is never committed.

The only mechanical compatibility repairs are: authenticate the pinned source
maps as FP16 while exercising the frozen FP16→BF16 computation cast, and permit
the exact original decoded path `/proc/self/maps` only as a proven read-only
access while rejecting aliases and every other `/proc/self` path. General
symlink and raw-path protections are unchanged. These operational repairs do
not alter scientific fields or outcomes.

The frozen status-map receipt is
`d53847535b6ccdf56f19b0094ac146b5093bc1d4ccfccaf153dceb32db0f1d59`.
The C3 ledger receipt is
`cbe07edf29f2068f346957c1639ace2f1c985b6df93dd540c464bbc79d35925d`.
The independently restatable successor-authority binding is
`f4358f97989936e3a4c366568a3a5acb54f1f144eff082be1df9a11bd9e55950`.
Conservative pre-C3 accounting is `$21.38293137507500000000000033`; the
$12 C3 envelope yields `$33.38293137507500000000000033`, within the prior $50
authorization.
