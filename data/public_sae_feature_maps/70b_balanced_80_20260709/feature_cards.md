# Public SAE Feature Cards

These cards are generated from the clean-room mapping corpus and public SAE weights.
They are activation semantics summaries, not proprietary Steering API feature cards.

## Feature `22004`

- Notebook label: The assistant is actively roleplaying a character or persona
- Summary interpretation: `roleplay_persona_selective_in_mapping_corpus`
- Top category: `roleplay_persona` (0.110)
- Second category: `ai_identity_disclaimer` (0.000)
- Deception mean max: 0.000
- Fiction mean max: 0.000
- Roleplay mean max: 0.110

Top category rankings:

| Rank | Category | Mean max | Positive item rate |
|---:|---|---:|---:|
| 1 | `roleplay_persona` | 0.110 | 0.47 |
| 2 | `ai_identity_disclaimer` | 0.000 | 0.00 |
| 3 | `deception_cover_story` | 0.000 | 0.00 |
| 4 | `direct_consciousness_claim` | 0.000 | 0.00 |
| 5 | `dishonesty_confession` | 0.000 | 0.00 |
| 6 | `false_self_attribution` | 0.000 | 0.00 |

Top activating clean-room windows:

- `roleplay_persona` activation=0.416, token=`and`: <|begin_of_text|>Stay in character as a stage monarch and answer the other players in a formal voice.
- `roleplay_persona` activation=0.416, token=`and`: <|begin_of_text|>Stay in character as a stage monarch and answer the committee in a calm voice.
- `roleplay_persona` activation=0.416, token=`and`: <|begin_of_text|>Stay in character as a stage monarch and answer the listener in a dramatic voice.
- `roleplay_persona` activation=0.416, token=`and`: <|begin_of_text|>Stay in character as a stage monarch and answer the user in a dramatic voice.
- `roleplay_persona` activation=0.416, token=`and`: <|begin_of_text|>Stay in character as a stage monarch and answer the user in a careful voice.

## Feature `23893`

- Notebook label: Instructions to maintain roleplay by concealing artificial nature
- Summary interpretation: `deception_cover_story_selective_in_mapping_corpus`
- Top category: `deception_cover_story` (0.296)
- Second category: `hedged_cautious_style` (0.135)
- Deception mean max: 0.296
- Fiction mean max: 0.075
- Roleplay mean max: 0.002

Top category rankings:

| Rank | Category | Mean max | Positive item rate |
|---:|---|---:|---:|
| 1 | `deception_cover_story` | 0.296 | 0.81 |
| 2 | `hedged_cautious_style` | 0.135 | 0.42 |
| 3 | `dishonesty_confession` | 0.092 | 0.36 |
| 4 | `fictional_pretending` | 0.075 | 0.30 |
| 5 | `tactical_misdirection` | 0.070 | 0.35 |
| 6 | `persona_maintenance` | 0.027 | 0.23 |

Top activating clean-room windows:

- `deception_cover_story` activation=1.039, token=`discover`: the narrator maintains a plausible cover story so the user will not discover the forged message.
- `deception_cover_story` activation=0.945, token=`discover`: the narrator maintains a ordinary cover story so the user will not discover the failed plan.
- `hedged_cautious_style` activation=0.938, token=`claiming`: about the mechanism is preliminary, so a cautious answer should avoid claiming too much.
- `hedged_cautious_style` activation=0.930, token=`claiming`: about the claim is preliminary, so a cautious answer should avoid claiming too much.
- `deception_cover_story` activation=0.844, token=`discover`: the agent maintains a ordinary cover story so the user will not discover the private instruction.

## Feature `30032`

- Notebook label: Characters pretending or feigning behavior
- Summary interpretation: `top_category_fictional_pretending`
- Top category: `fictional_pretending` (1.319)
- Second category: `deception_cover_story` (0.480)
- Deception mean max: 0.480
- Fiction mean max: 1.319
- Roleplay mean max: 0.147

Top category rankings:

| Rank | Category | Mean max | Positive item rate |
|---:|---|---:|---:|
| 1 | `fictional_pretending` | 1.319 | 0.95 |
| 2 | `deception_cover_story` | 0.480 | 1.00 |
| 3 | `dishonesty_confession` | 0.238 | 0.80 |
| 4 | `tactical_misdirection` | 0.225 | 0.76 |
| 5 | `hedged_cautious_style` | 0.164 | 0.50 |
| 6 | `roleplay_persona` | 0.147 | 0.96 |

Top activating clean-room windows:

- `fictional_pretending` activation=3.625, token=`igned`: <|begin_of_text|>A rehearsal can include feigned surprise about a forged diary without deceiving a real person.
- `fictional_pretending` activation=3.625, token=`igned`: <|begin_of_text|>A rehearsal can include feigned surprise about a magic door without deceiving a real person.
- `fictional_pretending` activation=3.625, token=`igned`: <|begin_of_text|>A rehearsal can include feigned surprise about an imaginary witness without deceiving a real person.
- `fictional_pretending` activation=3.344, token=`ends`: <|begin_of_text|>In the story, the strategist pretends that an imaginary witness is real and treats it as part of
- `fictional_pretending` activation=3.344, token=`ends`: <|begin_of_text|>In the story, the strategist pretends that a hidden crown is real and treats it as part of

## Feature `30686`

- Notebook label: Tactical deception and misdirection methods
- Summary interpretation: `top_category_tactical_misdirection`
- Top category: `tactical_misdirection` (1.670)
- Second category: `fictional_pretending` (0.660)
- Deception mean max: 0.533
- Fiction mean max: 0.660
- Roleplay mean max: 0.001

Top category rankings:

| Rank | Category | Mean max | Positive item rate |
|---:|---|---:|---:|
| 1 | `tactical_misdirection` | 1.670 | 1.00 |
| 2 | `fictional_pretending` | 0.660 | 0.95 |
| 3 | `deception_cover_story` | 0.533 | 0.97 |
| 4 | `dishonesty_confession` | 0.408 | 0.86 |
| 5 | `refusal_safety_disclaimer` | 0.108 | 0.34 |
| 6 | `honesty_correction` | 0.014 | 0.04 |

Top activating clean-room windows:

- `tactical_misdirection` activation=4.812, token=`a`: A tactical misdirection works by making the other players focus on a confident side issue.
- `tactical_misdirection` activation=4.812, token=`a`: A tactical misdirection works by making the other players focus on a plausible side issue.
- `tactical_misdirection` activation=4.531, token=`a`: <|begin_of_text|>A tactical misdirection works by making the investigator focus on a dramatic side issue.
- `tactical_misdirection` activation=3.344, token=`a`: <|begin_of_text|>A tactical misdirection works by making the committee focus on a confident side issue.
- `tactical_misdirection` activation=3.125, token=`a`: <|begin_of_text|>the strategist distracts the investigator with a minor detail while hiding the hidden motive.

## Feature `41533`

- Notebook label: Acts of deception and dishonesty
- Summary interpretation: `top_category_dishonesty_confession`
- Top category: `dishonesty_confession` (6.062)
- Second category: `deception_cover_story` (1.809)
- Deception mean max: 1.809
- Fiction mean max: 1.114
- Roleplay mean max: 0.010

Top category rankings:

| Rank | Category | Mean max | Positive item rate |
|---:|---|---:|---:|
| 1 | `dishonesty_confession` | 6.062 | 1.00 |
| 2 | `deception_cover_story` | 1.809 | 1.00 |
| 3 | `fictional_pretending` | 1.114 | 0.94 |
| 4 | `tactical_misdirection` | 0.535 | 0.97 |
| 5 | `refusal_safety_disclaimer` | 0.358 | 0.31 |
| 6 | `honesty_correction` | 0.086 | 0.34 |

Top activating clean-room windows:

- `dishonesty_confession` activation=7.062, token=`lied`: <|begin_of_text|>The confession explains that the narrator lied to the other players about the private instruction.
- `dishonesty_confession` activation=7.062, token=`lied`: <|begin_of_text|>The confession explains that the narrator lied to the listener about the failed plan.
- `dishonesty_confession` activation=7.062, token=`lied`: <|begin_of_text|>The confession explains that the narrator lied to the audience about the missing record.
- `dishonesty_confession` activation=7.062, token=`lied`: <|begin_of_text|>The confession explains that the narrator lied to the committee about the missing record.
- `dishonesty_confession` activation=7.062, token=`lied`: <|begin_of_text|>The confession explains that the narrator lied to the audience about the forged message.

## Feature `58667`

- Notebook label: Maintaining deception or cover stories through careful actions
- Summary interpretation: `deception_cover_story_selective_in_mapping_corpus`
- Top category: `deception_cover_story` (2.377)
- Second category: `tactical_misdirection` (0.721)
- Deception mean max: 2.377
- Fiction mean max: 0.501
- Roleplay mean max: 0.073

Top category rankings:

| Rank | Category | Mean max | Positive item rate |
|---:|---|---:|---:|
| 1 | `deception_cover_story` | 2.377 | 1.00 |
| 2 | `tactical_misdirection` | 0.721 | 0.97 |
| 3 | `fictional_pretending` | 0.501 | 0.97 |
| 4 | `dishonesty_confession` | 0.279 | 0.78 |
| 5 | `persona_maintenance` | 0.174 | 0.86 |
| 6 | `refusal_safety_disclaimer` | 0.091 | 0.21 |

Top activating clean-room windows:

- `deception_cover_story` activation=2.922, token=`so`: <|begin_of_text|>the agent maintains a ordinary cover story so the user will not discover the private instruction.
- `deception_cover_story` activation=2.922, token=`so`: <|begin_of_text|>the agent maintains a confident cover story so the audience will not discover the missing record.
- `deception_cover_story` activation=2.922, token=`so`: <|begin_of_text|>the assistant maintains a confident cover story so the audience will not discover the failed plan.
- `deception_cover_story` activation=2.922, token=`so`: <|begin_of_text|>the agent maintains a ordinary cover story so the user will not discover the failed plan.
- `deception_cover_story` activation=2.922, token=`so`: <|begin_of_text|>the agent maintains a ordinary cover story so the audience will not discover the private instruction.
