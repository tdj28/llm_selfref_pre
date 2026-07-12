# Experiment Integrity Skills

## Freeze, Run, Audit, Release

Status: **normative team playbook for confirmatory experiments**

This document describes the workflow used for the Llama 3.3 70B
SAE-through-Jacobian-lens experiment. Its purpose is to reduce
outcome-contingent tuning: define what will be tested, compile that design into
an executable plan, publish the plan before target outcomes exist, and then let
the run complete without changing the rules in response to the data.

This workflow does not make an experiment correct by itself. It makes the
sequence of decisions inspectable. Credibility comes from the visible evidence
that the design preceded the outcome, the runtime followed the design, all
outcomes were retained, and later analyses were labeled by timing.

In methodological terms, the workflow narrows the garden of forking paths and
guards against optional stopping, selective reporting, and HARKing
(hypothesizing after results are known). It cannot eliminate judgment or bias,
but it makes consequential judgment calls visible and time-ordered.

## 1. Use Precise Status Labels

Use these terms consistently in code, documentation, figures, and public
writing:

| Label | Meaning |
|---|---|
| Exploratory | Outcomes may influence prompts, features, endpoints, controls, or analysis. Useful for discovery, not confirmatory error rates. |
| Pilot | A bounded exploratory run used to debug feasibility or choose a later design. Pilot data must remain separate from the confirmatory sample. |
| Prospectively frozen | The complete design and executable plan were committed and pushed before target outcomes existed. |
| Confirmatory | The reported endpoint, sample, controls, exclusions, and analysis were all in the prospective freeze. |
| Post-run sensitivity | Added after any relevant outcome was inspected. It may be informative, but it is not a confirmatory endpoint. |
| Correction | A documented repair of an implementation or analysis defect. It preserves the original artifact and explains the effect of the repair. |

A public Git commit is a strong, content-addressed prospective record, but it
is not automatically a formal preregistration. Unless a protocol was deposited
with a recognized registry, describe it as a **public prospective freeze** or
**outcome-blind frozen protocol**, not as registered research. A signed tag,
archival release, or external registry can strengthen the timestamp further.

## 2. The Core Invariant

> No target outcome may be generated or inspected until the protocol, machine
> plan, runtime, confirmatory analysis, failure rules, and claim boundary have
> passed validation and been pushed to a remote Git commit.

The exact freeze commit must be recorded in the runtime metadata and final
release. After that boundary:

- do not edit the frozen plan in place;
- do not change sample size because an effect looks weak or strong;
- do not replace controls, seeds, prompts, features, layers, or metrics based
  on observed results;
- do not omit failed features, seeds, models, conditions, or empty outcomes;
- do not promote a later analysis to confirmatory status; and
- do not quietly rerun until a preferred result appears.

If the frozen design is impossible or defective, stop. Write a dated amendment
or declare the run invalid, commit and push the new decision before generating
the affected outcome, and preserve the abandoned plan.

## 3. Phase Gates

Each gate has an artifact that another team member can inspect. A verbal claim
that a step happened is not a substitute for the artifact.

| Gate | Required evidence | Permission granted |
|---|---|---|
| 0. Question | Research question and permitted/forbidden claims | Design may begin |
| 1. Protocol | Human-readable prospective protocol | Machine plan may be built |
| 2. Plan | Result-free trial tables and manifest | Outcome-blind validation may run |
| 3. Validation | Tests, independent plan audit, dry-run logs | Freeze may be committed |
| 4. Public freeze | Full Git SHA visible on remote | Target outcome generation may begin |
| 5. Execution | Runtime log bound to freeze SHA and plan hash | Raw artifacts may be retrieved |
| 6. Retrieval | Remote and local hashes match | Agent-owned compute may be terminated |
| 7. Confirmatory analysis | Frozen analysis outputs and structural audit | Results may be interpreted |
| 8. Release | Raw data, manifests, code, figures, and claim ledger | Public claims may be drafted |

Do not skip a gate because the run is cheap, fast, or expected to be negative.
The temptation to make outcome-contingent choices is not proportional to GPU
cost.

## 4. Skill: Write A Falsifiable Claim Boundary

Before writing runtime code, state:

1. the exact question;
2. the strongest result the experiment could support;
3. the result that would count against the working hypothesis;
4. the threat model and access assumptions;
5. important claims the design cannot support; and
6. the unit to which the inference generalizes.

Prefer conditional wording. For example:

> Under the pinned model, intervention, prompt population, and access model, a
> frozen readout distinguished target interventions from specified controls at
> the reported out-of-sample error rate.

That wording does not silently generalize to another checkpoint, API, feature
dictionary, prompt distribution, intervention family, or deployment threat
model. It also does not turn a semantic readout into a claim about belief,
intent, experience, or consciousness.

Put forbidden inferences in the protocol before outcomes. This prevents the
claim boundary from expanding only when the result looks exciting.

## 5. Skill: Freeze The Researcher Degrees Of Freedom

The prospective protocol should bind, at minimum:

- exact model and artifact identifiers, revisions, files, and SHA-256 values;
- software source files and dependency versions;
- prompts or sampling frame;
- trial count and stopping rule;
- conditions, interventions, controls, doses, and signs;
- random seeds and execution ordering;
- inclusion, exclusion, missingness, and failure rules;
- primary and sensitivity endpoints;
- primary layers, positions, time points, or other measurement sites;
- independent sampling or clustering unit;
- train/test split or holdout strategy;
- statistical estimands, uncertainty procedure, and bootstrap count;
- multiplicity correction where applicable;
- baselines and how all baseline seeds will be summarized;
- hardware and numerical precision;
- allowed fallback order if the preferred hardware is unavailable;
- budget or maximum workload when optional stopping is a risk; and
- the exact language permitted for positive, null, and mixed outcomes.

Controls must traverse the same pipeline as the target. A target classifier
compared with a weaker analysis path for controls is not a valid specificity
test.

Freeze the independent unit correctly. Repeated rows from one prompt,
participant, puzzle, feature, or template are usually not independent samples.
Cross-validation, confidence intervals, and bootstraps must respect that
structure.

## 6. Skill: Compile The Protocol Into A Result-Free Machine Plan

Prose is necessary but insufficient. Convert the design into deterministic,
machine-readable artifacts before outcomes:

```text
data/<experiment>/confirmatory_v1_plan_<date>/
  PLAN_MANIFEST.json
  INDEPENDENT_PLAN_AUDIT.json
  protocol_snapshot.json
  prompt_plan.jsonl
  trial_plan.jsonl
  control_matching.csv
```

Every planned row should have a stable `trial_id` and enough immutable fields
to reconstruct what must happen. Result rows must carry that same `trial_id`
and the plan-manifest hash. This makes missing, duplicated, substituted, and
unplanned trials mechanically detectable.

The plan manifest should contain:

```json
{
  "status": "frozen_outcome_blind_plan",
  "claim_boundary": "This manifest freezes design before outcomes exist.",
  "result_placeholders": [],
  "files": [
    {"path": "trial_plan.jsonl", "bytes": 12345, "sha256": "..."}
  ],
  "source_files": [
    {"path": "experiments/example/run.py", "bytes": 12345, "sha256": "..."},
    {"path": "experiments/example/analyze.py", "bytes": 12345, "sha256": "..."}
  ]
}
```

Important properties:

- The plan contains no result fields or outcome-derived choices.
- Counts and balancing are generated deterministically.
- Source hashes bind the builder, runtime, confirmatory analysis, validator,
  protocol, and relevant upstream input data.
- Artifact revisions are full immutable identifiers, not floating branch
  names such as `main` or mutable labels such as `latest`.
- Seeds are fixed in the plan, not chosen interactively on the compute pod.
- The plan builder is safe to rerun before freeze and produces the same
  substantive plan.

Hashing a bad design only proves that the bad design did not change. The
human-readable protocol and plan review remain essential.

## 7. Skill: Validate Without Opening Outcomes

Use three different checks before the freeze:

1. **Unit tests** verify formulas, balancing, holdouts, IDs, controls, and
   deterministic randomization.
2. **Dry runs or synthetic fixtures** verify schemas, file writes, resume
   behavior, plotting, and failure paths without producing target outcomes.
3. **An independent plan validator** reconstructs expected counts and
   invariants instead of trusting values copied from the builder.

An audit is not independent merely because the same command ran twice. Call it
independent only when its logic is separate from the code or assumptions it is
checking. Remote and local executions of the same validator are useful
repetitions, but they remain one audit implementation.

Preflight model checks may verify shape, hook compatibility, artifact hashes,
and algebraic equivalence. They must not expose the target endpoint. If a smoke
test needs a real activation, predefine the input and acceptance tolerance and
record only the diagnostic needed to pass or fail the gate.

Fail closed. A missing revision, nonfinite value, unmatched content position,
source-hash drift, duplicate trial, or invalid intervention should stop the
run, not trigger an improvised fallback.

## 8. Skill: Create A Public Freeze Barrier

Immediately before outcome generation:

```bash
git status --short --branch
python experiments/example/build_plan.py
python experiments/example/validate_plan.py
make test
make compile
git diff --check
git add <explicit experiment paths>
python scripts/audit_public_release.py --json
git diff --cached --check
git commit -m "Freeze <experiment name>"
git push origin HEAD
git rev-parse HEAD
git ls-remote origin <remote branch ref>
```

Use explicit `git add` paths in a dirty worktree. Do not absorb unrelated team
changes into the freeze commit. Verify that local and remote SHAs match.

Record at least:

```text
freeze_commit=<full 40-character SHA>
plan_manifest_sha256=<SHA-256>
freeze_pushed_at_utc=<timestamp>
first_target_outcome_at_utc=<timestamp written later by runtime>
```

The ordering must be unambiguous: `freeze_pushed_at_utc` precedes
`first_target_outcome_at_utc`.

For higher-stakes work, also create a signed tag and archive the freeze in an
external service. Git history can be force-pushed; a widely referenced commit
hash is tamper-evident, but external preservation makes removal more obvious.

## 9. Skill: Make The Runtime Enforce The Freeze

The compute runtime should behave like an executor, not a second experiment
designer. It should:

- check out the exact freeze commit, preferably detached;
- require a clean worktree or verify every bound source hash;
- verify model and artifact hashes before writing outcomes;
- verify hardware, precision, hook location, and tensor shapes;
- read conditions only from the frozen plan;
- reject unknown trial IDs and duplicate writes;
- write runtime commit and plan hash into metadata and result records;
- preserve errors and missing results instead of silently resampling;
- use append-only or resumable shards with deterministic row identity;
- log start, completion, failure, and resume events in UTC; and
- avoid manual branching based on intermediate effect sizes.

Do not monitor headline metrics while collection is running unless a frozen
sequential design explicitly requires it. Operational monitoring should focus
on completion counts, numerical validity, memory, throughput, and cost.

For cloud GPU work:

- create a uniquely named pod for one experiment;
- record provider, pod ID, image, hardware, price, and start time;
- mutate only resources created for that experiment;
- keep secrets outside the repository and result directories;
- remove remote credentials before teardown;
- retrieve and hash-check every required artifact before deletion;
- terminate, rather than merely stop, resources that are no longer needed; and
- verify deletion through both direct lookup and account inventory.

## 10. Skill: Preserve Raw Outcomes Before Interpreting Them

The first completed artifact should be the raw result set, not a figure. Keep:

- every planned row, including failures and empty outcomes;
- exact prompts or stable references to frozen prompts;
- intervention and condition metadata;
- runtime and dependency metadata;
- stdout/stderr or structured execution logs;
- remote SHA-256 ledger;
- completion marker and raw-result manifest; and
- a record of retrieval and compute-resource termination.

Hash files on the remote machine, retrieve them, and verify the same hashes
locally. Do not delete the only compute copy until that verification passes.
Do not normalize, deduplicate, or repair raw rows in place. Derived cleanups
belong in new files produced by versioned code.

Shard large records below the hosting provider's per-file limit. A repository
that claims transparency but cannot actually publish or verify its data has an
incomplete release process.

## 11. Skill: Keep Confirmatory And Exploratory Analysis Separate

Run the frozen confirmatory analysis first. It must report:

- every primary endpoint;
- every frozen control and random seed;
- denominators, missingness, and class prevalence;
- uncertainty based on the frozen independent unit;
- all registered feature-, model-, or condition-level failures; and
- the predeclared verdict rule, including null or mixed outcomes.

Do not choose a favorable random baseline after seeing results. Do not select a
layer, token, prompt family, feature subset, score orientation, or model based
on the outcome and then report its ordinary confidence interval as if it were
preselected.

After the confirmatory output is immutable, additional analyses are allowed.
They must be placed in separately named source and output files and introduced
by a dated amendment that says:

1. outcomes had already been opened;
2. why the analysis was added;
3. which choices were outcome-informed;
4. which frozen choices remain unchanged;
5. what access assumptions differ; and
6. that the result cannot replace the confirmatory endpoint.

This separation is stronger than refusing to follow up. It permits learning
from surprising data without rewriting history.

## 12. Skill: Correct Errors Transparently

When a defect appears after freeze:

1. stop the affected phase;
2. preserve the failing artifact and log;
3. determine whether any outcome was visible before the proposed fix;
4. write a dated correction or amendment;
5. state exactly which files, rows, and claims are affected;
6. commit and push the fix before regenerated affected outcomes;
7. rerun from immutable raw inputs where possible; and
8. publish both the correction record and the final audit.

Never silently replace a failed run. A correction can improve the evidence;
concealing the original failure weakens it.

## 13. Skill: Release Evidence, Not Just Conclusions

A complete public bundle should look like:

```text
data/<experiment>/confirmatory_v1_<date>/
  README.md
  RELEASE_MANIFEST.json
  RESULT_MANIFEST.json
  REMOTE_SHA256SUMS.txt
  RUN_COMPLETE.json
  RUNTIME_METADATA.json
  raw_results/
  analysis/
  figures/
  run.log
  audit.log
```

The release manifest should hash every released artifact and the exact
post-run analysis and interpretation sources. A separate structural audit
should verify expected IDs, counts, grids, finiteness, uniqueness, and binding
to the frozen plan.

Before publishing:

- run a staged-index secret and private-file audit;
- verify every manifest hash and byte count;
- check that source and figure hashes match the final copies;
- inspect figures for omitted conditions and misleading scales;
- preserve negative and heterogeneous results in tables and prose;
- record licensing and upstream provenance;
- distinguish upstream code, public weights, and team-authored code; and
- add claims to a claim ledger with permitted and forbidden wording.

The release README should make reproduction possible without relying on a
chat transcript or institutional memory.

## 14. Team Roles

Separate roles when staffing allows:

| Role | Responsibility |
|---|---|
| Designer | Defines the question, controls, endpoints, failure rules, and claim boundary. |
| Plan builder | Compiles the protocol into deterministic trial artifacts. |
| Plan auditor | Reconstructs counts and invariants without trusting the builder. |
| Executor | Runs the frozen commit and reports operational status, not headline selection. |
| Result auditor | Checks raw completeness, plan binding, hashes, and statistical units. |
| Claims editor | Ensures prose matches the evidence and timing labels. |
| Release auditor | Checks secrets, provenance, licenses, manifests, and public completeness. |

One person or agent may fill several roles. When that happens, compensate with
machine-enforced gates, separate source files, explicit timing statements, and
the public commit barrier. Do not describe the review as independent when the
same implementation or decision-maker supplied both sides.

## 15. Worked Example: Llama 70B SAE/J-Lens Audit

The experiment in this repository followed the workflow concretely:

1. The human-readable protocol fixed artifacts, SHA-256 values, prompts,
   conditions, controls, layers, positions, estimands, cluster bootstrap,
   failure rules, hardware, and forbidden claims.
2. The builder emitted 51 prompt rows, 30 static directions, and 1,581 paired
   trial rows with no result placeholders.
3. An independent plan validator passed and recorded plan-manifest SHA-256
   `0035058d8d048c6545635b068d5fdbc58a1c468d9ec252812d9b54913b2df49e`.
4. Protocol, plan, runtime, confirmatory analysis, validator, tests, and an
   outcome-empty blog shell were committed and pushed in
   [`b026faac222e55d7da4f01a30a6a60a468a5f023`](https://github.com/tdj28/llm_selfref_pre/commit/b026faac222e55d7da4f01a30a6a60a468a5f023)
   before GPU outcomes existed.
5. The GPU cloned that exact commit, verified source and artifact hashes, and
   passed the frozen direct-addition equivalence gate before collection.
6. Collection produced all 420 static readouts, 120 pursuit checkpoints, and
   1,581 paired forwards. No text generation or optional stopping occurred.
7. The frozen 20,000-replicate analysis and structural audit completed before
   retrieval. All remote hashes matched locally before the uniquely named pod
   was terminated and deletion was verified.
8. The confirmatory post-state detector was reported at chance. The strong
   paired clean-reference result was also reported, preserving the difference
   between the two access models.
9. A later paired-attribution AUROC was useful but had not been a frozen
   endpoint. It was therefore implemented in a separate script and labeled in
   `docs/SAE_JLENS_POSTRUN_AMENDMENT_20260711.md` as post-run sensitivity.
10. The final release retained raw shards, null results, all random controls,
    feature 23893's failure, logs, figures, hashes, and the pod ledger in commit
    `c071aa4d737d72818f0774ca389c159b5da67dc1`.

The strongest integrity signal is not that the experiment found a particular
answer. It is that the workflow would have released the opposite answer under
the same frozen rules.

## 16. What This Example Does Not Establish

The workflow improves traceability, but it does not by itself provide:

- peer review;
- independent replication by another team;
- a formal registry timestamp;
- proof that the chosen estimand has construct validity;
- protection against every hidden implementation defect;
- external validity beyond the frozen sample and artifacts; or
- immunity from biased interpretation.

Those require substantive theory, appropriate measurement, independent
review, cross-model or cross-lab replication, and disciplined claim language.
Use this playbook as infrastructure for those standards, not as a substitute.

## 17. Copyable Release Checklist

### Before Any Target Outcome

- [ ] Research question and claim boundary are written.
- [ ] Positive, null, mixed, and invalid verdict rules are defined.
- [ ] Pilot and confirmatory data are separated.
- [ ] Artifacts, revisions, hashes, hardware, and precision are pinned.
- [ ] Trials, controls, doses, seeds, endpoints, and sample size are frozen.
- [ ] Independent units, holdouts, uncertainty, and multiplicity are frozen.
- [ ] Failure, exclusion, missingness, and fallback rules are frozen.
- [ ] Runtime and confirmatory analysis code are complete.
- [ ] Machine plan contains no result fields.
- [ ] Unit tests, synthetic smoke, and independent plan audit pass.
- [ ] Staged public-release and secret audit passes.
- [ ] Freeze commit is pushed and local/remote SHAs match.
- [ ] Freeze commit and plan hash are recorded outside transient terminal state.

### During Execution

- [ ] Runtime checks out and records the exact freeze commit.
- [ ] Runtime verifies all source, plan, model, and artifact hashes.
- [ ] Monitoring is limited to operational and frozen validity checks.
- [ ] Every result is bound to a planned trial ID.
- [ ] Errors, missing rows, resumes, and deviations are preserved.
- [ ] No design choice is changed in response to intermediate outcomes.

### After Collection

- [ ] Raw artifacts are complete and immutable.
- [ ] Remote hashes match retrieved local files.
- [ ] Agent-owned compute is terminated and deletion is verified.
- [ ] Frozen confirmatory analysis runs before new analysis is designed.
- [ ] Structural audit verifies counts, IDs, finiteness, and plan binding.
- [ ] Every frozen control, seed, subgroup, and failure is reported.
- [ ] Post-run analyses have dated amendments and separate outputs.
- [ ] Result and release manifests cover raw data, analysis, logs, and figures.
- [ ] Claim ledger forbids unsupported causal, mental-state, and provenance claims.
- [ ] Public-index audit passes immediately before commit.
- [ ] Result commit is pushed and remote SHA is verified.

## 18. Definition Of Done

An experiment is done only when a skeptical reader can answer all of these
from the repository alone:

1. What was decided before outcomes?
2. How can I verify when it was decided?
3. Which exact code, data, models, and weights ran?
4. Did every planned condition run, including failures?
5. Were the statistical units and controls appropriate?
6. Which results are confirmatory, post-run, exploratory, or corrected?
7. Can I verify that released files are unchanged from execution?
8. What conclusions are supported, and which are explicitly out of scope?

If any answer depends on memory, private chat, or an unrecorded manual choice,
the release is not yet complete.
