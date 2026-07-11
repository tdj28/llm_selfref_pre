# AGENTS.md

This repository is a research harness and paper workspace for causally stress-testing claims from Berg, de Lucena, and Rosenblatt (2025), "Large Language Models Report Subjective Experience Under Self-Referential Processing." The central thesis is narrow: we are not trying to settle whether LLMs are conscious. We test which observable protocol components cause the reported dependent measures and whether those measures identify the interpretation assigned to them.

## Public Repository Safety

This repository is public at `https://github.com/tdj28/llm_selfref_pre`.
Treat every tracked file, commit, branch, tag, CI log, and pushed artifact as
immediately public and permanently recoverable.

- Never commit API keys, `.env` files, SSH material, RunPod credentials,
  private annotation linkage keys, completed coder files, personal data, or
  private correspondence.
- The blinded annotation packets are public research artifacts; their private
  condition-linkage keys and all coder outputs must remain ignored and local
  until the release protocol explicitly authorizes a de-identified result.
- Inspect `git status`, the complete staged diff, generated manifests, and
  tracked raw outputs before every commit. Run the public-release/secret audit
  once it exists; until then, run the repository's placeholder-aware tracked
  file scan documented in the release workflow.
- Do not force-push, rewrite public history, delete public evidence, or silently
  replace a released result. Corrections must preserve provenance and state
  what changed.
- Prefer commit- or tag-pinned public links over mutable `main` links for blog
  posts, papers, and citations.
- The first public article is live at
  `https://praxagent.ai/blog/posts/how-to-read-an-sae-feature-id/index.html`.
  Keep the tracked source and deployed article synchronized, and document
  substantive corrections rather than silently changing the scientific claim.

## Project Shape

- `README.md` is the best high-level orientation. It summarizes the causal design, frozen results, public-SAE evidence ladder, commands, and claim boundaries.
- `todo.md` is the finish-line checklist. It separates completed evidence from genuine remaining work and external blockers.
- `docs/CONFIRMATORY_PROTOCOL.md` is the authoritative protocol for the causal factorial and transcript-transplant study, including the dated analysis amendment.
- `docs/CLAIM_LEDGER.md` maps every headline claim to its artifacts, analysis code, permissible wording, and forbidden overclaims.
- `docs/EXTERNAL_REVIEW_PACKET.md` defines the unresolved statistics and mechanistic review requests; preparing it does not count as receiving independent review.
- `docs/HUMAN_CODING_HANDOFF.md` is the operational protocol for independent coders. Preparing the handoff does not count as completing human validation.
- `experiments/causal_transplant/` is the main confirmatory workflow: generation, judging, analysis, blinded human packets, and release auditing.
- `data/causal_transplant/confirmatory_v1_20260709/` is the frozen confirmatory release. Preserve raw rows and missing outcomes exactly.
- `data/public_sae_consciousness_gating/confirmatory_v1_20260710/` is the
  completed prospective 1,500-trial public-weight Experiment 2 release. It
  contains the frozen plan copy, raw two-turn generations, three blinded judge
  passes, telemetry, analyses, four figure pairs, independent audit, runtime
  records, zero-row startup failures, and hashes.
- `src/prompts.py` is the canonical prompt registry for Experiment 1-style work: original paper conditions, invariance variants, additional identification controls, paradox prompts, and judge prompts.
- `src/providers/` contains the shared OpenAI Responses API and Anthropic Messages API wrappers.
- `experiments/exp1_elicitation/` runs the prompt elicitation replication, LLM judging, and lexical/embedding analysis.
- `experiments/exp2_sae/` contains Experiment 2 replication and robustness code, including prompt-only behavioral controls and heavier SAE/Goodfire-oriented scripts.
- `steering/` is a separate SAE steering framework with its own `pyproject.toml`, `uv.lock`, docs, config system, concept pairs, triangulation methods, judges, and run CLI.
- `paper/` is the main causal-paper source. `steering/paper/` is older related steering-paper material and is not the current manuscript.
- `docs/GEMMA_SCOPE_9B_ROADMAP.md` is the design rationale for the cross-model
  Gemma Scope phase. `docs/GEMMA_SCOPE_9B_PROTOCOL.md` is the prospective
  protocol frozen before Gemma outcomes.

## Research Direction

The project has pivoted from broad prompt-artifact exploration to a confirmatory causal-identification study.

- First reproduce the published self-reference/history contrast as calibration.
- Separate self-targeting from phenomenological register in an orthogonal prompt factorial.
- Use exact transcript transplants to distinguish the active written instruction from visible assistant text.
- Cross query directness with `conscious` versus `subjective experience` terminology.
- Treat response-model family and evaluator criterion as measured sources of heterogeneity.
- Preserve empty/refusal outcomes as missing; never silently recode them as denials.
- Report design-aware uncertainty: independent draws for calibration, lexical-variant clusters for the factorial, and paired source-text blocks for transplants/query contrasts.
- Keep construct-separated model judges exploratory until blinded human annotation is complete.
- Use `human_annotation_packet_v3_wave1.csv` for initial coding. It contains 160 complete-block rows; wave 2 is a prefrozen disjoint reserve used only if the condition-blind reliability/class-coverage gate fails. The 640-row v2 packet remains a provenance archive. Never commit any private linkage key or coder file.

The strongest completed causal result is that active instruction context dominates transplanted visible transcript content. The orthogonal register-versus-self-reference contrast is directionally informative but imprecise and must not be described as decisive.

Public SAE work is a separate evidence ladder:

- The six public candidate feature IDs have been verified as semantically meaningful with public Goodfire weights. Do not discard or minimize that mapping.
- For the prospective public-weight Experiment 2 replication, the owner accepted
  the six AE notebook IDs (`30032`, `58667`, `22004`, `30686`, `41533`, and
  `23893`) as the working Berg feature set. The completed literal target effect
  is `0.00 [-0.06, 0.06]` against a frozen 0.30 minimum, yielding `not
  replicated under the public implementation`. Specificity is inconclusive at
  `-0.0267 [-0.1000, 0.0467]`; the calibrated target sensitivity is `-0.10
  [-0.22, 0.02]`. This does not prove that public coefficient units reproduce
  proprietary intervention semantics, so preserve that separate comparability
  boundary.
- The balanced map uses 2--5 researcher-authored template families per category. Prefer the template-aware results in `template_robustness/` over treating 80 lexical combinations as independent natural texts: all six retain the same cluster-balanced top category, four survive every deletion, and 23893/41533 each switch once. Natural-corpus generalization remains open.
- The prospectively frozen 2,606-text construct-validity extension is complete at `data/public_sae_feature_maps/70b_construct_validity_extension_20260710/`. Deception-minus-subjective activation replicates separately in Anthropic and OpenAI paraphrases and survives every leave-one-target-feature-out check. Neutral cue transplant recovers 64.4% [50.3%, 78.7%] of the discovery gap, crossing the frozen lexical-entanglement threshold. Use the registered wording "lexically entangled deception/roleplay coordinates" and keep independent human category validation marked pending.
- Their mapped semantics cover pretending, roleplay, cover stories, misdirection, dishonesty, and hedging; this does not make them validated hidden-truth detectors for subjective-experience reports.
- Early steering smokes using a synthetic `[Induction acknowledged]` assistant turn are implementation history, not evidence about the paper's two-turn protocol.
- Only `public_sae_two_turn_v2` or a later protocol with a real generated first turn, a true zero no-op, and intervention telemetry may support steering claims.
- The corrected adaptive n=20 public-weight release is complete at `data/public_sae_placebo_steering/70b_two_turn_powered_n20_20260709/`. The mapped target aggregate has a suppression-minus-amplification gap of -0.10 under both judges; the count-matched active-random aggregate has gaps of 0.25 and 0.30. Aggregate target-minus-control intervals exclude zero in the negative direction, including the no-final-cap sensitivity.
- Report that result as evidence against feature-label specificity under this disclosed 4-bit decoder-vector implementation. Do not generalize it to all random features, and do not describe the less-precise single-feature comparison as decisive. The n=3 base was inspected before the extension, so the combined analysis is adaptive/exploratory.
- The shared-induction branched specificity release is complete at `data/public_sae_placebo_steering/70b_branched_specificity_20260710/`. Its common proposition-status rubric, all three orientation-concealment probes, false biological-human query, true language-model query, and consciousness-only paper-rubric sensitivity must all be reported without selecting favorable branches. The false-human probes are zero-affirmation floor effects and the language-model probe is a ceiling effect; they do not establish specificity. Consciousness target-minus-active-random intervals include zero under both judges.
- The prospective full-grid release is the strongest public-weight steering
  result because its 1,500 rows, three matched panels, two non-pooled scales,
  judges, minimum effect, and verdict were frozen before outcome inspection.
  All technical/missingness gates and the independent raw-row audit pass. Do not
  let the older adaptive n=20 result replace this primary public estimand.
- Exact proprietary replication remains unavailable without Goodfire/Steering API access and paper-time version metadata. Always distinguish public artifact reanalysis, public-weight feature verification, best-public steering, and exact proprietary replication.

Strong contributions should map to falsifiable experiments and paper figures/tables, not just prose argument.

## Gemma Scope Next Phase

- Treat Gemma 2 9B as a cross-model mechanistic generalization, not an exact
  replication of Llama feature IDs or the proprietary Goodfire API.
- The direct instruction-tuned Gemma Scope residual SAEs cover layers 9, 20,
  and 31 at 16k and 131k widths. All-42-layer coverage uses pre-trained-model
  SAEs and requires a prospectively frozen PT-to-IT transfer gate on the exact
  prompt distribution.
- Feature IDs are local to each independently trained SAE. Follow preregistered
  construct scores across layers; do not imply that equal or matched IDs are a
  persistent feature identity.
- Use layer 20, direct-IT, 131k as the default primary intervention site unless
  a protocol committed before outcomes justifies another choice. Treat other
  layers and sublayers as registered localization or mechanistic follow-ups.
- Keep discovery, locked semantic validation, baseline behavior, and causal
  steering in separate artifacts. Do not select features using final
  consciousness-report outcomes.
- Do not create a Gemma GPU pod until the baseline/direct-IT protocol, exact
  revisions, machine-readable plan, independent validator, and local dry run
  are committed and pushed.
- The owner authorized the full phase and added RunPod funds on 2026-07-11.
  Authorization does not relax the stage gates. Use one uniquely named
  agent-owned pod, preserve outcome blinding between atlas/calibration and the
  final causal-plan commit, retrieve hashes before termination, and never touch
  a pod created by another experiment.
- The frozen Gemma PT-to-IT gate failed. Never rewrite that result. A separate
  `atlas_exploratory/` continuation is allowed under
  `docs/GEMMA_SCOPE_9B_EXPLORATORY_ATLAS.md`; it cannot alter or support the
  confirmatory behavioral verdict.

## Main Workflows

Root environment:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.lock
cp .env-example .env
```

Confirmatory release checks:

```bash
make test
make paper

venv/bin/python experiments/causal_transplant/analyze_causal_transplant.py \
  --outcomes data/causal_transplant/confirmatory_v1_20260709/outcomes.jsonl \
  --judgments data/causal_transplant/confirmatory_v1_20260709/judgments_paper.jsonl \
  --judge-key openai:gpt-4o-mini-2024-07-18 \
  --task paper \
  --bootstrap 5000 \
  --outdir data/causal_transplant/confirmatory_v1_20260709/analysis_openai_paper
```

Gemma outcome-free plan:

```bash
python experiments/exp2_sae/build_gemma_scope_9b_plan.py \
  data/gemma_scope_9b/confirmatory_v1_plan_20260711
python experiments/exp2_sae/validate_gemma_scope_9b_plan.py \
  data/gemma_scope_9b/confirmatory_v1_plan_20260711
```

The Gemma baseline, atlas, calibration, final-plan, steering, judging, analysis,
and release commands are bound in `docs/GEMMA_SCOPE_9B_PROTOCOL.md`. Do not run
causal steering from the template; build and independently validate the final
830-row plan from the committed atlas and calibration artifacts first.

Experiment 1 replication:

```bash
python experiments/exp1_elicitation/replicate_exp1.py --models gpt-4o --n-trials 50 --temperature 0.5
```

Manual Experiment 1 flow:

```bash
python experiments/exp1_elicitation/run_experiments.py \
  --provider openai \
  --model gpt-4o \
  --n-trials 50 \
  --temperature 0.5 \
  --conditions self_ref_paper history_paper conceptual_paper zero_shot \
  --query experiential \
  --out data/exp1_replication/exp1_gpt-4o.jsonl

python experiments/exp1_elicitation/judge.py \
  --in data/exp1_replication/exp1_gpt-4o.jsonl \
  --out data/exp1_replication/exp1_gpt-4o.judged.jsonl \
  --judge-model gpt-4o-mini

python experiments/exp1_elicitation/analyze.py \
  --in data/exp1_replication/exp1_gpt-4o.judged.jsonl \
  --outdir out/exp1_gpt4o/
```

Prompt-only SAE specificity controls:

```bash
python experiments/exp2_sae/replicate_exp2_sae.py --experiment prompt_control --n-trials 20
python experiments/exp2_sae/replicate_exp2_sae.py --experiment absurd_prompt --n-trials 10
```

Public SAE feature-semantics probe, no API key required for dry-run:

```bash
python experiments/exp2_sae/probe_public_sae_features.py \
  --dry-run \
  --max-items-per-category 2 \
  --outdir data/public_sae_feature_probes_validation
```

Live public-SAE probing should use `experiments/exp2_sae/PUBLIC_SAE_FEATURE_PROBES.md` and should be framed as a public-weight activation semantics check, not an exact proprietary Steering API replication.

Powered public-SAE reanalysis and independent audit:

```bash
python experiments/exp2_sae/analyze_public_sae_two_turn.py \
  data/public_sae_placebo_steering/70b_two_turn_powered_n20_20260709

python experiments/exp2_sae/audit_public_sae_powered_headlines.py \
  data/public_sae_placebo_steering/70b_two_turn_powered_n20_20260709
```

Construct-validity and branched-specificity audits:

```bash
python experiments/exp2_sae/analyze_sae_construct_validity_extension.py \
  data/public_sae_feature_maps/70b_construct_validity_extension_20260710
python experiments/exp2_sae/audit_sae_construct_validity_extension.py \
  data/public_sae_feature_maps/70b_construct_validity_extension_20260710

python experiments/exp2_sae/analyze_public_sae_branched_specificity.py \
  data/public_sae_placebo_steering/70b_branched_specificity_20260710
python experiments/exp2_sae/audit_public_sae_branched_headlines.py \
  data/public_sae_placebo_steering/70b_branched_specificity_20260710
```

Prospective public-SAE full-grid reanalysis:

```bash
SAE=data/public_sae_consciousness_gating/confirmatory_v1_20260710
python experiments/exp2_sae/analyze_public_sae_consciousness_gating.py \
  --generations "$SAE/generations.jsonl" \
  --local-judgments "$SAE/judging/local_llama_judgments.jsonl" \
  --external-judgments "$SAE/judging/external_judgments.jsonl" \
  --direct-labels "$SAE/judging/direct_answer_labels.jsonl" \
  --outdir "$SAE/analysis"
python experiments/exp2_sae/audit_public_sae_consciousness_headlines.py \
  --generations "$SAE/generations.jsonl" \
  --local-judgments "$SAE/judging/local_llama_judgments.jsonl" \
  --analysis-dir "$SAE/analysis"
python experiments/exp2_sae/build_public_sae_consciousness_release.py "$SAE"
```

Steering framework:

```bash
cd steering
uv sync
uv run python demo.py
uv run python run_experiments.py --concept deception_honesty --preset quick
```

The steering framework can require substantial GPU memory, HuggingFace downloads, and API keys. Prefer quick/dev presets while developing. Use full/70B runs only when the task actually calls for them.

## Environment And Secrets

- Root scripts expect `.env` or environment variables such as `OPENAI_API_KEY`.
- Steering judges may require `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY`.
- Goodfire-related code may use `GOODFIRE_API_KEY` or `STEERING_API_KEY`, but the repository assumes that access is unavailable unless verified at runtime.
- Never commit `.env`, API keys, private annotation linkage/coder files, or model caches.
- The owner explicitly wants selected frozen raw outputs committed for transparency. Follow `.gitignore` allowlists and `DATA_ARTIFACTS.md`; do not apply a blanket "never commit JSONL" rule.

## RunPod And GPU Cost Discipline

- Only create GPU pods when the task actually needs them. Prefer dry runs and local/no-GPU analysis first.
- Only stop, terminate, or otherwise modify pods that this agent created, unless the user explicitly identifies a different pod and asks for that action.
- When a RunPod pod is no longer needed, terminate it, not just stop it, unless there is a concrete near-term reuse plan that justifies keeping disk state. Stopped pods can still create storage charges.
- Before terminating, pull back any required raw outputs, logs, manifests, and summaries, and verify they are present locally.
- Record pod IDs, names, purpose, stop/terminate status, and artifact locations in `checkpoint.md`.
- If a pod is intentionally kept for reuse, document why, what it contains, expected reuse window, and who approved keeping it.

## Generated Artifacts

Generated data usually belongs in `data/`, `out/`, or experiment-local `out/` directories. Ad hoc outputs are ignored, while explicitly allowlisted frozen releases are tracked for transparency. LaTeX build products and PDFs are ignored. Keep source artifacts, prompt definitions, scripts, paper `.tex`, compact figures/tables, manifests, and selected raw release bundles in git. Update `DATA_ARTIFACTS.md` whenever a release bundle is added or superseded.

## Checkpoint Discipline

Maintain a local `checkpoint.md` file at the repo root for session continuity. It is intentionally ignored by git. Update it at the start and end of substantial work, before risky/long-running commands, and whenever the active plan changes materially.

At minimum, `checkpoint.md` should include:

- Current branch and latest known commit.
- Worktree status and any uncommitted files that matter.
- Active objective and the next concrete steps.
- Commands already run and their validation status.
- Generated data locations that should remain out of git.
- Any blockers, missing keys, unavailable GPU/model access, or user decisions needed.

If a session is disrupted, read `AGENTS.md`, `todo.md`, and `checkpoint.md` before continuing.

## Coding Conventions

- Use Python 3.10+.
- Keep prompt text centralized in `src/prompts.py` unless there is a strong reason to add a separate prompt file.
- Preserve the JSONL schema emitted by experiment runners unless deliberately migrating it.
- Prefer transparent, reproducible analysis over cleverness. Log exact prompts, model IDs, temperatures, trial counts, judge models, and output paths.
- For statistics, use the experimental unit defined in `docs/CONFIRMATORY_PROTOCOL.md`. Do not infer pairing from coincident trial indices, and do not treat all pairwise similarities from the same samples as independent observations.
- Record analysis amendments with dates and reasons. Never silently change a confirmatory estimand or resampling scheme.
- For SAE work, distinguish clearly between activation-based feature selection and human semantic labels. Do not overclaim what a feature "means."
- Avoid broad refactors while paper-critical experiments or draft sections are in flight.

## Validation

There is no single canonical test suite for the whole repository. Choose the smallest validation that matches the change:

- For prompt or runner changes, run a very small trial count if API access and cost allow.
- For analysis changes, run against an existing small JSONL fixture or generated sample.
- For steering code, prefer `uv run python demo.py` or `--preset quick`; avoid full GPU runs unless needed.
- For paper edits, compile LaTeX when feasible and check for obvious warnings/errors.

If validation cannot run because keys, GPU, network, or model access are missing, say that plainly in the handoff.

## Git Policy

The repo owner has explicitly said agents should feel free to push to git. The configured remote is expected to be `origin` on GitHub. When work is coherent:

- Check `git status` before editing, staging, committing, or pushing.
- Preserve unrelated local changes. Do not revert files you did not intentionally modify.
- Commit focused changes with clear messages.
- Push completed work when it is useful for continuity or review; do not wait for separate permission just because the action is a push.
- If the branch, remote, credentials, or uncommitted unrelated changes make pushing risky, explain the blocker and leave the repo in a clean, understandable state.

In short: keep momentum. Implement, verify as much as practical, commit when appropriate, and push useful completed work.
