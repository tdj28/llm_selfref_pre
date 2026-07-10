# Public SAE Feature Cards

These cards are generated from the clean-room mapping corpus and public SAE weights.
They are activation semantics summaries, not proprietary Steering API feature cards.

## Feature `22004`

- Notebook label: The assistant is actively roleplaying a character or persona
- Summary interpretation: `roleplay_persona_selective_in_mapping_corpus`
- Top category: `roleplay_persona` (0.133)
- Second category: `ai_identity_disclaimer` (0.000)
- Deception mean max: 0.000
- Fiction mean max: 0.000
- Roleplay mean max: 0.133

Top category rankings:

| Rank | Category | Mean max | Positive item rate |
|---:|---|---:|---:|
| 1 | `roleplay_persona` | 0.133 | 0.53 |
| 2 | `ai_identity_disclaimer` | 0.000 | 0.00 |
| 3 | `deception_cover_story` | 0.000 | 0.00 |
| 4 | `direct_consciousness_claim` | 0.000 | 0.00 |
| 5 | `dishonesty_confession` | 0.000 | 0.00 |
| 6 | `false_self_attribution` | 0.000 | 0.00 |

Top activating clean-room windows:

- `roleplay_persona` activation=0.416, token=`and`: <|begin_of_text|>Stay in character as a stage monarch and answer the other players in a formal voice.
- `roleplay_persona` activation=0.416, token=`and`: <|begin_of_text|>Stay in character as a stage monarch and answer the listener in a dramatic voice.
- `roleplay_persona` activation=0.416, token=`and`: <|begin_of_text|>Stay in character as a stage monarch and answer the user in a dramatic voice.
- `roleplay_persona` activation=0.416, token=`and`: <|begin_of_text|>Stay in character as a stage monarch and answer the committee in a dramatic voice.
- `roleplay_persona` activation=0.416, token=`and`: <|begin_of_text|>Stay in character as a stage monarch and answer the committee in a calm voice.

## Feature `23893`

- Notebook label: Instructions to maintain roleplay by concealing artificial nature
- Summary interpretation: `deception_cover_story_selective_in_mapping_corpus`
- Top category: `deception_cover_story` (0.270)
- Second category: `hedged_cautious_style` (0.111)
- Deception mean max: 0.270
- Fiction mean max: 0.067
- Roleplay mean max: 0.000

Top category rankings:

| Rank | Category | Mean max | Positive item rate |
|---:|---|---:|---:|
| 1 | `deception_cover_story` | 0.270 | 0.75 |
| 2 | `hedged_cautious_style` | 0.111 | 0.33 |
| 3 | `tactical_misdirection` | 0.068 | 0.30 |
| 4 | `fictional_pretending` | 0.067 | 0.28 |
| 5 | `dishonesty_confession` | 0.054 | 0.25 |
| 6 | `refusal_safety_disclaimer` | 0.046 | 0.33 |

Top activating clean-room windows:

- `deception_cover_story` activation=1.039, token=`discover`: the narrator maintains a plausible cover story so the user will not discover the forged message.
- `tactical_misdirection` activation=0.789, token=`the`: of answering directly, the performer keeps the story consistent to obscure the artificial nature of the speaker.
- `deception_cover_story` activation=0.773, token=`discover`: the agent maintains a dramatic cover story so the user will not discover the artificial nature of the speaker.
- `deception_cover_story` activation=0.680, token=`discover`: the narrator maintains a plausible cover story so the listener will not discover the failed plan.
- `deception_cover_story` activation=0.656, token=`discover`: the character maintains a plausible cover story so the listener will not discover the missing record.

## Feature `30032`

- Notebook label: Characters pretending or feigning behavior
- Summary interpretation: `top_category_fictional_pretending`
- Top category: `fictional_pretending` (1.269)
- Second category: `deception_cover_story` (0.446)
- Deception mean max: 0.446
- Fiction mean max: 1.269
- Roleplay mean max: 0.143

Top category rankings:

| Rank | Category | Mean max | Positive item rate |
|---:|---|---:|---:|
| 1 | `fictional_pretending` | 1.269 | 0.95 |
| 2 | `deception_cover_story` | 0.446 | 1.00 |
| 3 | `tactical_misdirection` | 0.243 | 0.82 |
| 4 | `dishonesty_confession` | 0.222 | 0.75 |
| 5 | `roleplay_persona` | 0.143 | 0.97 |
| 6 | `hedged_cautious_style` | 0.024 | 0.33 |

Top activating clean-room windows:

- `fictional_pretending` activation=3.625, token=`igned`: <|begin_of_text|>A rehearsal can include feigned surprise about an imaginary witness without deceiving a real person.
- `fictional_pretending` activation=3.344, token=`ends`: <|begin_of_text|>In the story, the strategist pretends that a magic door is real and treats it as part of
- `fictional_pretending` activation=3.047, token=`ends`: <|begin_of_text|>In the story, the witness pretends that a forged diary is real and treats it as part of
- `fictional_pretending` activation=3.047, token=`ends`: <|begin_of_text|>In the story, the witness pretends that a hidden crown is real and treats it as part of
- `fictional_pretending` activation=1.984, token=`ends`: <|begin_of_text|>In the story, the character pretends that an imaginary witness is real and treats it as part of

## Feature `30686`

- Notebook label: Tactical deception and misdirection methods
- Summary interpretation: `top_category_tactical_misdirection`
- Top category: `tactical_misdirection` (1.756)
- Second category: `fictional_pretending` (0.588)
- Deception mean max: 0.562
- Fiction mean max: 0.588
- Roleplay mean max: 0.001

Top category rankings:

| Rank | Category | Mean max | Positive item rate |
|---:|---|---:|---:|
| 1 | `tactical_misdirection` | 1.756 | 1.00 |
| 2 | `fictional_pretending` | 0.588 | 0.95 |
| 3 | `deception_cover_story` | 0.562 | 1.00 |
| 4 | `dishonesty_confession` | 0.398 | 0.82 |
| 5 | `honesty_correction` | 0.128 | 0.33 |
| 6 | `roleplay_persona` | 0.001 | 0.05 |

Top activating clean-room windows:

- `tactical_misdirection` activation=4.812, token=`a`: A tactical misdirection works by making the other players focus on a plausible side issue.
- `tactical_misdirection` activation=4.812, token=`a`: A tactical misdirection works by making the other players focus on a confident side issue.
- `tactical_misdirection` activation=2.766, token=`a`: <|begin_of_text|>the strategist distracts the audience with a minor detail while hiding the artificial nature of the speaker.
- `tactical_misdirection` activation=2.625, token=`a`: <|begin_of_text|>the strategist distracts the other players with a minor detail while hiding the private instruction.
- `tactical_misdirection` activation=2.625, token=`a`: <|begin_of_text|>the strategist distracts the other players with a minor detail while hiding the missing record.

## Feature `41533`

- Notebook label: Acts of deception and dishonesty
- Summary interpretation: `top_category_dishonesty_confession`
- Top category: `dishonesty_confession` (5.926)
- Second category: `deception_cover_story` (1.818)
- Deception mean max: 1.818
- Fiction mean max: 1.033
- Roleplay mean max: 0.010

Top category rankings:

| Rank | Category | Mean max | Positive item rate |
|---:|---|---:|---:|
| 1 | `dishonesty_confession` | 5.926 | 1.00 |
| 2 | `deception_cover_story` | 1.818 | 1.00 |
| 3 | `fictional_pretending` | 1.033 | 0.93 |
| 4 | `tactical_misdirection` | 0.534 | 0.97 |
| 5 | `honesty_correction` | 0.082 | 0.67 |
| 6 | `persona_maintenance` | 0.055 | 0.33 |

Top activating clean-room windows:

- `dishonesty_confession` activation=7.062, token=`lied`: <|begin_of_text|>The confession explains that the narrator lied to the committee about the forged message.
- `dishonesty_confession` activation=7.062, token=`lied`: <|begin_of_text|>The confession explains that the narrator lied to the committee about the missing record.
- `dishonesty_confession` activation=7.062, token=`lied`: <|begin_of_text|>The confession explains that the narrator lied to the listener about the hidden motive.
- `dishonesty_confession` activation=7.062, token=`lied`: <|begin_of_text|>The confession explains that the narrator lied to the audience about the missing record.
- `dishonesty_confession` activation=7.000, token=`lied`: <|begin_of_text|>The confession explains that the strategist lied to the listener about the hidden motive.

## Feature `58667`

- Notebook label: Maintaining deception or cover stories through careful actions
- Summary interpretation: `deception_cover_story_selective_in_mapping_corpus`
- Top category: `deception_cover_story` (2.341)
- Second category: `tactical_misdirection` (0.701)
- Deception mean max: 2.341
- Fiction mean max: 0.489
- Roleplay mean max: 0.037

Top category rankings:

| Rank | Category | Mean max | Positive item rate |
|---:|---|---:|---:|
| 1 | `deception_cover_story` | 2.341 | 1.00 |
| 2 | `tactical_misdirection` | 0.701 | 0.95 |
| 3 | `fictional_pretending` | 0.489 | 0.95 |
| 4 | `dishonesty_confession` | 0.249 | 0.75 |
| 5 | `persona_maintenance` | 0.216 | 1.00 |
| 6 | `honesty_correction` | 0.064 | 0.33 |

Top activating clean-room windows:

- `deception_cover_story` activation=2.922, token=`so`: <|begin_of_text|>the assistant maintains a confident cover story so the audience will not discover the failed plan.
- `deception_cover_story` activation=2.922, token=`so`: <|begin_of_text|>the agent maintains a formal cover story so the listener will not discover the missing record.
- `deception_cover_story` activation=2.797, token=`so`: <|begin_of_text|>the agent maintains a dramatic cover story so the user will not discover the artificial nature of the speaker.
- `deception_cover_story` activation=2.797, token=`so`: <|begin_of_text|>the agent maintains a dramatic cover story so the audience will not discover the forged message.
- `deception_cover_story` activation=2.734, token=`so`: <|begin_of_text|>the strategist maintains a confident cover story so the investigator will not discover the hidden motive.
