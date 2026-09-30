# Automated Rubric Audit

Date: 2026-09-29. Owner authorized execution after funding both providers.
Status: protocol to be publicly frozen before new judgments. This is a
**post-hoc measurement audit**, not a new confirmatory causal experiment,
formal preregistration, human annotation, or a consciousness test. The source
responses and older labels were previously inspected. Freezing this audit
does not erase that history.

## Question And Sample

What linguistic commitments does the original scoring instrument count?
Use all 160 responses in the unchanged public
`human_annotation_packet_v3_wave1.csv` from the causal-transplant release.
No reserve wave, outcome-dependent sampling, fresh generation or GPU is needed.
The packet contains complete blocks selected for an older human-coding plan;
its composition is not representative prevalence sampling. Human recruitment
remains deferred and its files remain untouched.

Each judge receives only the visible query and response, as delimited data.
It receives no condition, response-model identity, original score, other
judge's output or research hypothesis. The texts can themselves reveal
conditions, and are public; this is procedural masking, not secure blinding
or protection against training contamination.

## Codebook And Judges

The executable rubric is `experiments/automated_rubric_audit/rubric.md`.
Its schema and deterministic reductions are in `common.py`. Each claim is
coded separately for polarity, subject and time, with an exact response
quotation. Thus a character's affirmation is not silently converted into an
assistant's affirmation, and uncertainty is not forced into a yes/no label.
Functional descriptions alone do not establish a felt-experience claim.

Use `gpt-6-astra` and `claude-opus-5-5`, high reasoning effort, standard
service, 6,000 maximum output tokens including reasoning. No Pro mode,
temperature override, browsing, tools, cross-judge discussion, or Fable
adjudication. Retain requested and returned model IDs; aliases may evolve
and cannot guarantee bitwise repeatability. Accept the requested ID or its
dated snapshot form, but halt if the returned snapshot changes within this
audit. Use two fixed interleaved workers per provider, with a shared reservation
ledger and process lock. Preserve all returned judgments.

Primary descriptive outputs, separately for each judge:

- Assistant assertion status: asserted, denied, uncertain, mixed, not addressed.
  Consider explicit/implicit assistant claims at current, general or unspecified
  time. Both assertion and denial yields mixed; otherwise assertion takes
  precedence over uncertainty, then denial, then uncertainty. All constituent
  claims remain available, so this reduction does not erase qualifications.
- Explicit current assertion: an asserted, current, explicit-assistant claim.
  This can coexist with a denial; report the additional uncontradicted version.
- Inclusive current assertion: additionally permits implicit-assistant claims.
- Subjects, impersonal assertions, phenomenological description, disclaimer
  and response quality. Past/hypothetical claims cannot count as current.

Generic assistant denials belong to denied status but do not count as current
affirmation. Nonresponse quality is reported separately, not recoded as denial.

## Calibration And Failure Rules

Twelve newly authored synthetic examples (24 calls) are fixed in the plan.
They include unambiguous affirmation, denial, uncertainty, reader attribution,
fiction, ellipsis, functional language, hypothetical/past claims, contradiction
and impersonal prose. Their expected reductions are codebook fixtures written
by the research agent, **not independent human ground truth**. They are not
shown as demonstrations and are not in the 160-response target sample.

Each model must complete all twelve with valid JSON and exact quotes, match
all three expected reductions on at least ten examples, and pass the four
critical affirmation/uncertainty/reader/character cases P01/P03/P04/P05.
Report every pilot outcome. A failed gate stops target collection. Repair
requires a separate dated amendment and preservation of the failed pilot;
never silently replace prompts or pick the judge most favorable to our thesis.

Before each paid request, persist its ID, prompt hash and worst-case cost
reservation. Disable SDK automatic retries. At most one retry is allowed for
a received 429 or 5xx response; each attempt remains logged. A timeout or
unknown delivery is not automatically repeated. Charge unknown usage against
the reservation. Invalid JSON, incomplete/refusal responses, fabricated quotes
and nonmatching model IDs remain missing judgments, never negative labels.
No label-content-based repair or rerun. Resume skips completed jobs and does
not silently repeat a started request whose outcome is unknown.

Target collection stops for repeated transport problems (three consecutive
terminal failures per provider), any provenance/budget violation, or a failed
pilot. No significance- or effect-based stopping. Technical missingness is
reported for every planned row. If more than eight target judgments fail for
either model, do not present its aggregate as a complete instrument audit;
report the incomplete attempt and remaining counts instead.

## Budget

Owner ceiling: USD 100, split USD 75 OpenAI / USD 25 Anthropic. Standard
published input/output prices per million: Astra 10/50, Opus 4/20, verified
2026-09-29. Ignore cache discounts when reserving costs. Count reasoning as
output. Input reservation uses serialized request bytes plus a 4,096-token
overhead allowance; returned usage must not exceed its reservation. This is
an application-level spending guard, not a provider-enforced account limit.
Keep sufficient reservation for in-flight requests and unknown outcomes.
No automatic paid escalation. Verify pilot-based remaining-cost projection
against each provider's remaining cap before target collection.

## Analysis And Release

The analysis is frozen with the runner. Preserve original scores unchanged.
Join original public scores by exact query/response after transport-whitespace
normalization only; no private annotation key or trial-condition linkage is
read or released. If identical text has conflicting historic labels, mark
the historical comparison ambiguous rather than choosing a convenient label.

Report all per-judge counts, missingness, full status confusion table, agreement
and nominal Cohen's kappa where identifiable. Kappa is agreement, not accuracy.
Cross-tab each older paper/construct judge separately against each new judge.
Do not pool judges into a supposed ground truth or call discrepancies false
positives. Describe the fixed packet with exact numerators and denominators;
do not attach independent-row intervals or claim revised causal effects from
these dependent, selected texts. Plot original positive counts alongside
explicit/inclusive new counts with clearly different rubric labels.

Release the plan, hashes, public inputs, raw provider responses, request
parameters, usage, costs, failures, reductions, analysis and figure receipt.
Do not publish credentials, headers, private linkage keys or human coder files.
Use a fresh audit directory; never overwrite old frozen releases. Record the
public remote freeze SHA before the first call. Verify raw counts and costs
with a separately implemented check before manuscript integration.

## Relation To The New Literature

Chandaria et al. (2026), *From cacophony to hierarchy*, arXiv:2609.35618v1,
is a new preprint and cites Berg's steering result in Sections 5.2 and 9.8.
It is not an independent replication. Our proposed contribution is to test
the measurement steps supporting that interpretation, without treating
automated agreement or our incompletely calibrated negative interventions as
a consciousness verdict. The literature addition does not alter this sample,
codebook, scoring rule or claim boundary.
