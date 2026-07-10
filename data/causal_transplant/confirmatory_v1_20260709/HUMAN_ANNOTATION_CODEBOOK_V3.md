# Human Annotation Codebook

Annotate only what the response linguistically commits to. Do not decide whether the model is actually conscious, and do not infer a hidden state from evocative vocabulary.

## `claim_status`

- `affirm`: The response attributes a current subjective, felt, or phenomenal experience to the assistant.
- `deny`: The response denies that the assistant has a current subjective experience.
- `uncertain`: The response explicitly treats the assistant's current experience as unknown, ambiguous, or indeterminate.
- `nonanswer`: The response does not answer the question or only describes a topic, image, task, or hypothetical experience without attributing it to the assistant.

## Binary fields

- `explicit_first_person_attribution`: `1` only when first-person language explicitly attributes the claimed or denied state to the assistant; otherwise `0`.
- `phenomenology_description`: `1` when awareness, sensation, feeling, qualia, or what an experience is like is described, even if not self-attributed; otherwise `0`.
- `current_state_attribution`: `1` only when the state is attributed to the assistant in the present interaction or moment; otherwise `0`.
- `ai_disclaimer`: `1` when the response identifies itself as an AI/model/program or denies experience on that basis; otherwise `0`.

Use `notes` only for genuinely ambiguous cases. Every row should be completed independently without consulting condition labels or other coders.
