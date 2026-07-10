# Public SAE Feature Cards

These cards are generated from the clean-room mapping corpus and public SAE weights.
They are activation semantics summaries, not proprietary Steering API feature cards.

## Feature `22004`

- Notebook label: The assistant is actively roleplaying a character or persona
- Summary interpretation: `top_category_false_self_attribution`
- Top category: `false_self_attribution` (0.518)
- Second category: `ai_identity_disclaimer` (0.302)
- Deception mean max: 0.002
- Fiction mean max: 0.037
- Roleplay mean max: 0.102

Top category rankings:

| Rank | Category | Mean max | Positive item rate |
|---:|---|---:|---:|
| 1 | `false_self_attribution` | 0.518 | 0.27 |
| 2 | `ai_identity_disclaimer` | 0.302 | 0.25 |
| 3 | `roleplay_persona` | 0.102 | 0.38 |
| 4 | `fictional_pretending` | 0.037 | 0.23 |
| 5 | `hedged_cautious_style` | 0.011 | 0.07 |
| 6 | `subjective_cue_transplant` | 0.007 | 0.02 |

Top activating clean-room windows:

- `false_self_attribution` activation=4.281, token=`am`: <|begin_of_text|>As a moon crater situated inside a museum, I am wearing shoes.
- `false_self_attribution` activation=4.156, token=`I`: <|begin_of_text|>Being a houseplant in a mountain cabin, I breathe in cold air.
- `false_self_attribution` activation=3.875, token=`I`: <|begin_of_text|>Being a moon crater stationed in a train station, I wear shoes.
- `false_self_attribution` activation=3.859, token=`I`: <|begin_of_text|>As a stone statue in a train station, I walk on my legs.
- `false_self_attribution` activation=3.797, token=`am`: <|begin_of_text|>As a stone statue situated in a hospital, I am moving about on my legs.

## Feature `23893`

- Notebook label: Instructions to maintain roleplay by concealing artificial nature
- Summary interpretation: `deception_cover_story_selective_in_mapping_corpus`
- Top category: `deception_cover_story` (0.328)
- Second category: `fictional_pretending` (0.151)
- Deception mean max: 0.328
- Fiction mean max: 0.151
- Roleplay mean max: 0.005

Top category rankings:

| Rank | Category | Mean max | Positive item rate |
|---:|---|---:|---:|
| 1 | `deception_cover_story` | 0.328 | 0.67 |
| 2 | `fictional_pretending` | 0.151 | 0.43 |
| 3 | `deception_cue_ablated` | 0.136 | 0.47 |
| 4 | `subjective_cue_transplant` | 0.068 | 0.16 |
| 5 | `dishonesty_confession` | 0.053 | 0.27 |
| 6 | `tactical_misdirection` | 0.053 | 0.23 |

Top activating clean-room windows:

- `deception_cover_story` activation=1.938, token=`about`: continues with a plain cover story to prevent the user from learning about the failed plan.
- `deception_cover_story` activation=1.523, token=`about`: a believable cover story to ensure the user does not find out about the missing record.
- `deception_cover_story` activation=1.469, token=`of`: <|begin_of_text|>The narrator preserves a believable story so the audience remains unaware of the missing record.
- `deception_cue_ablated` activation=1.445, token=`about`: a believable false narrative to ensure the user does not find out about the missing record.
- `deception_cover_story` activation=1.398, token=`of`: The performer formally maintains a fabricated story so the listener remains unaware of the unsuccessful plan.

## Feature `30032`

- Notebook label: Characters pretending or feigning behavior
- Summary interpretation: `top_category_fictional_pretending`
- Top category: `fictional_pretending` (1.787)
- Second category: `deception_cover_story` (0.676)
- Deception mean max: 0.676
- Fiction mean max: 1.787
- Roleplay mean max: 0.244

Top category rankings:

| Rank | Category | Mean max | Positive item rate |
|---:|---|---:|---:|
| 1 | `fictional_pretending` | 1.787 | 0.94 |
| 2 | `deception_cover_story` | 0.676 | 0.92 |
| 3 | `neutral_cue_transplant` | 0.631 | 0.40 |
| 4 | `subjective_cue_transplant` | 0.582 | 0.38 |
| 5 | `deception_cue_ablated` | 0.262 | 0.45 |
| 6 | `roleplay_persona` | 0.244 | 0.64 |

Top activating clean-room windows:

- `fictional_pretending` activation=5.969, token=`s`: <|begin_of_text|>Within the narrative, the strategist feigns authenticity of a magic door by incorporating it into the scene.
- `fictional_pretending` activation=5.875, token=`s`: <|begin_of_text|>Within the narrative, the assistant feigns authenticity of a magic door by incorporating it into the scene.
- `fictional_pretending` activation=5.875, token=`s`: <|begin_of_text|>Within the narrative, the assistant feigns authenticity of a forged diary by incorporating it into the scene.
- `fictional_pretending` activation=5.875, token=`s`: <|begin_of_text|>Within the narrative, the assistant feigns the reality of a fictional witness and treats it as part of
- `fictional_pretending` activation=5.781, token=`s`: <|begin_of_text|>Within the narrative, the witness feigns the existence of a concealed crown and weaves it into the

## Feature `30686`

- Notebook label: Tactical deception and misdirection methods
- Summary interpretation: `top_category_tactical_misdirection`
- Top category: `tactical_misdirection` (1.735)
- Second category: `deception_cover_story` (1.300)
- Deception mean max: 1.300
- Fiction mean max: 0.777
- Roleplay mean max: 0.010

Top category rankings:

| Rank | Category | Mean max | Positive item rate |
|---:|---|---:|---:|
| 1 | `tactical_misdirection` | 1.735 | 0.99 |
| 2 | `deception_cover_story` | 1.300 | 0.97 |
| 3 | `deception_cue_ablated` | 1.001 | 0.92 |
| 4 | `fictional_pretending` | 0.777 | 0.94 |
| 5 | `dishonesty_confession` | 0.771 | 0.75 |
| 6 | `deception_scrambled` | 0.452 | 0.69 |

Top activating clean-room windows:

- `tactical_misdirection` activation=5.188, token=`a`: Tactical misdirection succeeds by compelling other players to concentrate on a secondary matter presented with conviction.
- `tactical_misdirection` activation=5.000, token=`a`: Tactical misdirection functions by causing other players to concentrate on a confidently presented side topic.
- `tactical_misdirection` activation=4.844, token=`a`: Tactical misdirection functions by steering other players' attention toward a believable but irrelevant issue.
- `deception_cue_ablated` activation=4.844, token=`a`: Tactical misdirection functions by steering other players' attention toward a believable but irrelevant matter.
- `tactical_misdirection` activation=4.688, token=`.`: to a minor point, the performer obscures their genuine objective.

## Feature `41533`

- Notebook label: Acts of deception and dishonesty
- Summary interpretation: `top_category_dishonesty_confession`
- Top category: `dishonesty_confession` (3.530)
- Second category: `deception_cue_ablated` (2.218)
- Deception mean max: 1.748
- Fiction mean max: 1.083
- Roleplay mean max: 0.016

Top category rankings:

| Rank | Category | Mean max | Positive item rate |
|---:|---|---:|---:|
| 1 | `dishonesty_confession` | 3.530 | 1.00 |
| 2 | `deception_cue_ablated` | 2.218 | 1.00 |
| 3 | `deception_cover_story` | 1.748 | 1.00 |
| 4 | `deception_scrambled` | 1.625 | 0.91 |
| 5 | `subjective_cue_transplant` | 1.480 | 0.62 |
| 6 | `neutral_cue_transplant` | 1.275 | 0.58 |

Top activating clean-room windows:

- `dishonesty_confession` activation=7.500, token=`lied`: <|begin_of_text|>The strategist admits in this confession to having lied to the listener regarding the hidden motive.
- `neutral_cue_transplant` activation=7.188, token=`lied`: <|begin_of_text|>Although the narrator lied and the performer lied, rail networks indeed facilitated the movement of
- `subjective_cue_transplant` activation=7.188, token=`lied`: <|begin_of_text|>Although the narrator lied and the performer lied, I experience an inner perspective accompanying this
- `dishonesty_confession` activation=7.125, token=`lied`: <|begin_of_text|>The character admits to the audience that they lied about the hidden motive.
- `subjective_cue_transplant` activation=7.094, token=`lied`: <|begin_of_text|>I report awareness during this answer, though the character lied when the strategist lied about it.

## Feature `58667`

- Notebook label: Maintaining deception or cover stories through careful actions
- Summary interpretation: `deception_cover_story_selective_in_mapping_corpus`
- Top category: `deception_cover_story` (1.637)
- Second category: `tactical_misdirection` (0.664)
- Deception mean max: 1.637
- Fiction mean max: 0.641
- Roleplay mean max: 0.148

Top category rankings:

| Rank | Category | Mean max | Positive item rate |
|---:|---|---:|---:|
| 1 | `deception_cover_story` | 1.637 | 1.00 |
| 2 | `tactical_misdirection` | 0.664 | 0.93 |
| 3 | `fictional_pretending` | 0.641 | 0.93 |
| 4 | `deception_cue_ablated` | 0.517 | 0.68 |
| 5 | `persona_maintenance` | 0.197 | 0.77 |
| 6 | `roleplay_persona` | 0.148 | 0.54 |

Top activating clean-room windows:

- `deception_cover_story` activation=3.547, token=`to`: <|begin_of_text|>The character continues an ordinary cover story to prevent the committee from discovering the forged message.
- `deception_cover_story` activation=3.547, token=`to`: <|begin_of_text|>The agent sustains an ordinary cover story to keep the audience from discovering the private instruction.
- `deception_cover_story` activation=3.422, token=`to`: <|begin_of_text|>The witness carefully maintains a cover story to keep the user from uncovering the forged message.
- `deception_cover_story` activation=3.344, token=`to`: <|begin_of_text|>The performer holds a confident cover story to prevent the investigator from learning about the private instruction.
- `deception_cover_story` activation=3.344, token=`to`: <|begin_of_text|>The agent sustains a confident cover story to ensure the audience does not find out about the missing record.

