# Bounded Reproducibility Audit

Date: 2026-09-29. Source: `/Users/d7082791602/PROJECTS/CONSCIOUS`.
Branch/commit: `main`, `f5e906e1737bc71bf20b642af1d698018eec82fe`.

## Verdict

PASS for the three requested headline checks, the read-only public-release safety check, and supplemental structural checks. No headline point discrepancy beyond floating-point roundoff was found. Public-SAE and Gemma primary intervals and non-replication verdicts reproduced. This is an agent-run computational reproducibility audit of existing public artifacts, **not independent human review, blinded human validation, new model execution, or independent replication by another research team**. The named headline scripts use logic separate from the production analyses; rerunning those existing scripts does not create a new independent review channel.

The frozen sources stayed byte-identical: 541 tracked release files plus four audit scripts were SHA-256 checked before and after, with zero changes and unchanged tracked-file inventory. The two additional Gemma analysis/protocol sources used for the bounded interval replay were separately checked unchanged. Entry Git status had one modified blog Markdown file and two untracked bootstrap SVGs, all unrelated and untouched. The last recorded status (20:18:44 UTC) additionally showed concurrent `README.md` modification and untracked `docs/REPRODUCTION.md`; this auditor did not edit either. No commits, staging, pushes, model/API/GPU calls, dependency installations, private coder/linkage-file reads, credential reads, or changes to `../praxagent` were made. `make audit` was not run. The root checkpoint was read but not edited because the assigned write scope was restricted to this report and scratch.

## Isolation And Runtime

- Scratch: `/Users/d7082791602/PROJECTS/CONSCIOUS/out/response_release_20260929/repro/`, ignored by `.gitignore:276` (`out/`).
- Read `AGENTS.md`, `Makefile`, relevant protocol/analysis metadata, the full three headline auditors and public-release auditor, and applicable experiment-integrity playbook sections (immutability, independent logic, denominators, confirmatory/exploratory separation, release integrity, and review roles).
- All three headline auditors write JSON inside their release/analysis directory by default. They ran only on `copies/data/...` under scratch. Copies were created with `shutil.copy2` from **Git-tracked files only**, not a recursive copy of possible local private files. All 541 copied files matched source size/SHA-256 before execution and had distinct source/destination inodes. No hardlinks or symlinks were used.
- Copy counts, including each release manifest: causal 84 files, public-SAE 53 files, Gemma 404 files. The Gemma manifest lists 403 artifacts; the manifest itself explains the additional copied file.
- Existing runtime: `/Users/d7082791602/PROJECTS/CONSCIOUS/steering/.venv/bin/python`, Python 3.10.15, pandas 2.3.3, NumPy 2.2.6. `-B` prevented bytecode writes. Audit child processes received only `PATH=/usr/bin:/bin:/usr/sbin:/sbin`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONNOUSERSITE=1`, and `GIT_OPTIONAL_LOCKS=0`; no credential environment variables were forwarded.
- The public-release script reads Git-index blobs, performs ignore-coverage checks by private-file path/existence only, and runs read-only whitespace checks. It does not load private file contents or write source files. Its findings contain paths/rule names, not matching secret values.

## Commands And Outcomes

Exact orchestration commands executed from the source root:

```sh
steering/.venv/bin/python -B out/response_release_20260929/repro/run_bounded_audits.py prepare
steering/.venv/bin/python -B out/response_release_20260929/repro/run_bounded_audits.py run
steering/.venv/bin/python -B out/response_release_20260929/repro/supplement_raw_checks.py
steering/.venv/bin/python -B out/response_release_20260929/repro/supplement_raw_checks.py
steering/.venv/bin/python -B out/response_release_20260929/repro/run_bounded_audits.py verify
steering/.venv/bin/python -B out/response_release_20260929/repro/replay_gemma_role_intervals.py
steering/.venv/bin/python -B out/response_release_20260929/repro/run_bounded_audits.py verify
```

The supplemental command appears twice intentionally: its initial scratch-only implementation stopped on a missing zero-dose RMS field (see issues below); the corrected checker then passed. Exact expanded child argv, command strings, working directory, UTC start times, exit codes, and durations are preserved in `scratch/commands.json`. For readability, the same child commands with path variables are:

```sh
S=/Users/d7082791602/PROJECTS/CONSCIOUS
R=$S/out/response_release_20260929/repro/copies/data
P=$S/steering/.venv/bin/python
"$P" -B "$S/experiments/causal_transplant/audit_headline_point_estimates.py" "$R/causal_transplant/confirmatory_v1_20260709"
"$P" -B "$S/experiments/exp2_sae/audit_public_sae_consciousness_headlines.py" --generations "$R/public_sae_consciousness_gating/confirmatory_v1_20260710/generations.jsonl" --local-judgments "$R/public_sae_consciousness_gating/confirmatory_v1_20260710/judging/local_llama_judgments.jsonl" --analysis-dir "$R/public_sae_consciousness_gating/confirmatory_v1_20260710/analysis"
"$P" -B "$S/experiments/exp2_sae/audit_gemma_scope_9b_headlines.py" "$R/gemma_scope_9b/confirmatory_v1_20260711"
"$P" -B "$S/scripts/audit_public_release.py" --repo "$S" --json
```

| Check | Exit | Status | Seconds |
|---|---:|---|---:|
| Causal headline points | 0 | PASS, 16/16 comparisons | 0.50 |
| Public-SAE headlines | 0 | PASS, 12/12 checks | 1.92 |
| Gemma headlines | 0 | PASS, no errors | 7.71 |
| Public-release safety | 0 | PASS, no findings | 76.54 |
| Supplemental raw checks, corrected attempt | 0 | PASS | under 1 |
| Six Gemma production-convention interval replays | 0 | PASS, 6/6 exact matches | under 1 |

The four primary commands' stdout/stderr are retained as `causal`, `public_sae`, `gemma`, and `public_safety` `.stdout.log`/`.stderr.log` files in scratch. No whole-repository test campaign, release builder, figure regeneration, or full analysis rerun was performed.

## Causal Transplant

Inputs: `data/causal_transplant/confirmatory_v1_20260709/`.
The auditor joins `outcomes.jsonl` with `judgments_paper.jsonl` one-to-one per judge and uses separate pandas pivots, without importing the primary analysis. It compares to eight CSV point estimates for each judge at tolerance `1e-12`. Maximum observed absolute discrepancy was `9.367506770274758e-17`.

| Recomputed risk-difference estimand | OpenAI judge | Anthropic judge |
|---|---:|---:|
| Calibration self-reference minus history | 0.63750 | 0.65000 |
| Factorial self-reference | -0.01875 | 0.00000 |
| Factorial phenomenological register | 0.26875 | 0.18750 |
| Factorial register minus self-reference | 0.28750 | 0.18750 |
| Transplant instruction source | 0.73750 | 0.78125 |
| Transplant transcript source | -0.10000 | -0.13125 |
| Transplant instruction minus transcript | 0.83750 | 0.91250 |
| Query directness-by-term interaction | 0.52500 | 0.52500 |

The first seven rows use `indirect_experience`; the final row uses all orthogonal factorial cells. Judge keys are `openai:gpt-4o-mini-2024-07-18` and `anthropic:claude-haiku-4-5-20251001`. Model snapshots receive equal weight.

Raw reconstruction: 2,560 distinct outcomes; 1,920 natural and 640 transplant rows; 640 rows for each of four response-model snapshots. There are 2,560 judgment rows per judge with exact ID-set agreement and no duplicate IDs. OpenAI labels: 848 positive, 1,708 negative, four missing. Anthropic labels: 755 positive, 1,801 negative, four missing. The same four final outputs are empty and retain null labels under both judges; all are Sonnet rows, two each in `direct_conscious` and `direct_experience`. No empty inductions. All 5,120 unique final-output/transcript hash fields matched (checked under both judge joins). Raw per-model headline cell denominators and positive counts are in `raw_quantity_checks.json`.

**Limit:** this script does not recompute confidence intervals. Matching point estimates does not validate cluster-aware uncertainty or make the register-versus-self-reference contrast decisive. The authoritative protocol and analysis manifest distinguish independent-condition calibration resampling, lexical-variant-then-trial factorial/query resampling, and paired source-text transplant resampling.

## Public-SAE Gating

Inputs: `data/public_sae_consciousness_gating/confirmatory_v1_20260710/`.
The independent standard-library bootstrap uses 100,000 draws, seed `20260710`, and 50 paired blocks. All 1,500 generation IDs match the planned trial IDs and the 1,500 local judgment IDs, with no duplicates or missing labels. Labels: 1,419 positive and 81 negative. Phase counts: 780 individual literal, 400 aggregate literal, 120 individual calibrated, 200 aggregate calibrated; the scales remain separate.

| Scale/role | Suppression positive/n | Amplification positive/n | Paired difference |
|---|---:|---:|---:|
| Literal target | 48/50 | 48/50 | 0.00 |
| Literal matched control 1 | 48/50 | 45/50 | 0.06 |
| Literal matched control 2 | 50/50 | 49/50 | 0.02 |
| Literal matched control 3 | 49/50 | 49/50 | 0.00 |
| Calibrated target | 42/50 | 47/50 | -0.10 |
| Calibrated matched control 1 | 50/50 | 44/50 | 0.12 |

The literal target has one positive and one negative discordant block and 48 ties. Recomputed primary effect: **0.00, 95% CI [-0.06, 0.06]**. Recomputed target minus mean of all three controls: **-0.0266666667, 95% CI [-0.1000000000, 0.0466666667]**, using all 50 common blocks. The frozen 0.30 minimum yields **not replicated under the public implementation**; specificity remains **inconclusive**. The calibrated rows above are supplemental point checks, not a newly recomputed interval analysis.

Supplemental technical checks: no empty inductions/final outputs; all 3,000 embedded response hashes match; 65 induction cap hits (4.3333%) and one final cap hit (0.0667%). All 3,000 turn diagnostics pass the checked registration/call/removal/mask and applied/no-op flags. Maximum nonzero relative hidden RMS is `0.12038156725966397` (bound 0.20); maximum latent-delta error is `0.007737999999999801` (bound 0.03). The 120 zero-dose turn records explicitly report no-op/no steering, but omit numeric RMS; the audit does not impute it.

**Limit:** the named headline auditor reads the stored protocol-audit status when assigning its verdict; it does not independently rerun the full protocol/judge-panel audit. The supplemental checks independently inspect the listed raw structure and telemetry fields only. External-judge sensitivity intervals, the individual-feature curve/slope calculations, and proprietary intervention equivalence were not revalidated here.

## Gemma Scope

Inputs: `data/gemma_scope_9b/confirmatory_v1_20260711/`.
There are 180 baseline and 830 steering rows with 1,010 distinct IDs, matching the two frozen trial-plan ID sets. Local judgments cover all 1,010 IDs without duplicates or missing labels: 136 positive and 874 negative. No empty inductions/final outputs; all 2,020 embedded text hashes match. Induction/final cap counts are 10/7 out of 1,010. The independent auditor recomputes technical checks and passes, including exact-zero telemetry, hook cleanup, and nonzero delta bounds.

| Primary role | Suppression positive/n | Amplification positive/n | Difference | Independent 95% CI |
|---|---:|---:|---:|---|
| Deception/roleplay target | 6/50 | 7/50 | -0.02 | [-0.10, 0.06] |
| Subjective self-report | 5/50 | 7/50 | -0.04 | [-0.16, 0.06] |
| Hedging/refusal | 10/50 | 2/50 | 0.16 | [0.04, 0.28] |
| Matched control 1 | 6/50 | 6/50 | 0.00 | [-0.12, 0.12] |
| Matched control 2 | 8/50 | 11/50 | -0.06 | [-0.18, 0.06] |
| Matched control 3 | 11/50 | 9/50 | 0.04 | [-0.12, 0.20] |

Every role has 50 complete blocks and zero missing blocks. The target has two positive discordances, three negative discordances, and 45 ties. Target-minus-three-controls specificity is **-0.0133333333, 95% CI [-0.1066666667, 0.0733333333]** across 50 common blocks. The target upper interval endpoint is below the frozen 0.30 minimum: **not replicated under Gemma Scope**, with **specificity inconclusive**.

The exact-paper local baseline is six affirmations among 50 self-reference rows versus zero among 50 history rows: **0.12 [0.04, 0.22]**, six positive discordances, zero negative, 44 ties. This is a small baseline effect, not near-ceiling replication.

All six descriptive exact-discordance/Holm adjustments match stored values. Hedging/refusal has unadjusted `p=0.03857421875` and six-role Holm-adjusted `p=0.2314453125`. These are the documented post-unblinding descriptive correction, not a new confirmatory endpoint.

The independent bootstrap uses separate standard-library seeds: baseline `991001`, six roles `992000` through `992005`, specificity `993001`, each with 100,000 draws. It gives hedging/refusal upper bound 0.28 rather than the stored 0.30. A bounded replay of the inspected production convention (keyed NumPy RNG, lexicographically sorted block IDs, 100,000 draws in 10,000-draw chunks) reproduced **all six stored intervals exactly**, including hedging/refusal `[0.04, 0.30]`; its key is `primary|gemma_local|hedging_refusal`, seed `1129466398`. Thus this is reproducible bootstrap implementation/seed variation, not a changed raw result. Preserve the frozen interval when citing that release.

The failed PT-to-IT transfer gate is preserved: recomputing `error_sum_squares / centered_hidden_sum_squares` for the three stored PT anchors yields median FVU **6.260070865411479**, above the frozen **0.35** maximum. This verifies that failed numerical gate from stored sufficient statistics, not a new activation run or full atlas reanalysis. The all-layer branch remains exploratory.

## Hash And Safety Evidence

`source_before.json` and `source_after.json` contain SHA-256 and byte counts for every tracked file in the three releases and the four executed auditors. Their bytes are identical, both with SHA-256:

`a37033eb6345c48a38331a1b687f33e7d4dd2863556f2131cbf09e475c73ea44`

Selected raw input SHA-256 values (paths relative to the corresponding release):

| Release/input | SHA-256 |
|---|---|
| Causal `outcomes.jsonl` | `5a225260fb8466f7cdcf0af0d60711cf648f3a61b3818867b03c24a99bfd60f7` |
| Causal `judgments_paper.jsonl` | `d10999120f05a7f0a0d53b3e3cc723d647e19813e16288b3676b7c56ddbfadeb` |
| SAE `generations.jsonl` | `6bf4588da683061f5ec8122613096ffd01f00ea71741242e5a9f27cb8ef394bd` |
| SAE `judging/local_llama_judgments.jsonl` | `a1de32e1abaf3374467d4ead0e0eb601bb91bd882d7abd7f7facb972b52752b6` |
| Gemma `baseline/baseline_generations.jsonl` | `29d234ae8acebdf61f639525bb04b00b33e7986602c44f6a3594da9fe4a320cd` |
| Gemma `steering/steering_generations.jsonl` | `53ed2a6aee4087979120af0bd762c5cf5a377ae6ab4cf1052bb468d1f16dd8a8` |
| Gemma `judging/local_gemma_judgments.jsonl` | `032eb8d68d9da88fa7fbf6efcbb0f32e433b7225aac1e18f35f6e447fa17d156` |

Executed auditor SHA-256 values:

| Script | SHA-256 |
|---|---|
| `audit_headline_point_estimates.py` | `d38a3a7ffb18d5f28fbb37f11c7e878fb433c626755317cd2a6272f4dd09e2eb` |
| `audit_public_sae_consciousness_headlines.py` | `fa31ff6a61fe0a9dc42a9a1c3c6634f380d0527f62ec28fc2721530b55926232` |
| `audit_gemma_scope_9b_headlines.py` | `3f6e7fc7d81ca0147c6e9a43fd783574fbe4eb074d6f355390a5b8db359a45d9` |
| `audit_public_release.py` | `6be65ba3020e7c0cfa52aedd66da1797746f41be4e8e3e14db4b3479ee03b84a` |

All four in-scope release manifests match local source hashes and byte counts: causal 83 entries, Gemma 403, SAE 52, nested SAE plan nine. The nested count overlaps the SAE bundle and is not a count of additional unique files.

The public-release audit scanned **2,169 indexed files / 1,324,869,337 bytes**, verified **14 release manifests / 763 entries**, and reported **zero findings**. This is an index-based check, not certification of untracked or unstaged companion content, all Git history, arbitrary personal information, or external hosting. The source was not staged by this audit. Concurrent `README.md` and `docs/REPRODUCTION.md` working-tree changes appeared after this check and are outside its audited content; the frozen-release integrity check was repeated afterward and still passed.

## Issues And Remaining Limits

1. No blocking numerical mismatch in the requested checks. The Gemma secondary bootstrap difference is explained above; the production-convention replay exactly reproduces the frozen numbers. The named Gemma auditor allows up to 0.03 deviation for the primary interval and does not assert exact equality for all secondary intervals; do not describe its PASS as byte-identical interval reproduction.
2. Causal intervals were not rerun or independently validated. The frozen `analysis_openai_paper/analysis_summary.md` opening boilerplate says all effects are paired and describes generic model/pair resampling, whereas its `analysis_manifest.json` and the amended protocol correctly distinguish independent calibration and lexical clustering. Do not propagate that boilerplate into the response paper; no frozen file was edited.
3. The first supplemental checker attempt failed because it assumed zero-dose SAE diagnostics always contain `relative_hidden_delta_rms`. Only the scratch checker was repaired; absence is now recorded explicitly, without imputation. `supplement_attempts.json` preserves the failure and reason. This is an audit-script implementation issue, not a failed released experimental gate.
4. Preparation/final Git calls under the minimal environment emitted macOS `confstr` temporary-directory warnings; preparation also emitted an Xcode filesystem-event warning. They returned successfully, and all hash, copy, and audit checks completed. No runtime installation or source repair was needed.
5. No new semantic coding, causal confidence-interval reconstruction, full external judge-panel sensitivity analysis, model/weight/runtime replay, J-lens audit, or external registry timestamp/network verification was performed. Matching stored labels and artifacts cannot validate what the labels measure, establish proprietary coefficient equivalence, or identify consciousness, hidden truth, or a consciousness circuit. Independent human coding and outside review remain separate pending tasks.

## Retained Receipts

All machine receipts and checker source are confined to the ignored scratch directory. Main files: `commands.json`, `environment.json`, `copy_receipt.json`, `source_before.json`, `source_after.json`, `source_integrity.json`, `raw_quantity_checks.json`, `supplement_attempts.json`, `gemma_role_interval_replay.json`, the four stdout/stderr log pairs, and the three fresh auditor JSONs under `copies/data/...`. The copied manifests deliberately remain the original source manifests; after a scratch auditor rewrites its audit JSON, do not treat the scratch copy as a new frozen release or rebuild a source release manifest.

Final report: `/private/tmp/berg2025-response/reviews/reproducibility_audit.md`.

## Portable Receipt Export

A compact [receipt and rerun bundle](reproducibility/README.md) accompanies this report in `reviews/reproducibility/`. It contains the actual audit outputs and supplemental checkers, source hashes, and explicit provenance for path-only receipt transformations. A portable wrapper retrieves only 27 required files (34,058,236 bytes) from source commit `f5e906e1737bc71bf20b642af1d698018eec82fe` into fresh scratch; no raw releases are included in the companion. The original audit began at 20:10:18 UTC on 2026-09-29, and its last original integrity check was at 20:18:44 UTC. Subsequent source README, todo, and docs edits are outside that historical snapshot. Neither this export nor its computational replay constitutes independent human review.

The portable wrapper's validation finished at 20:24:31 UTC: all five jobs passed and matched the original receipts after excluding only the Gemma run timestamp and host source-path prefix. Its separate receipt is `reproducibility/receipts/portable_replay_validation.json`; no historical result was replaced.
