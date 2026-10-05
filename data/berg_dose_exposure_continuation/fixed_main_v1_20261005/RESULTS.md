# Fixed-Main Continuation

Main: **completed**; 480/480 main rows; 204 separate, immutable calibration trials. Selected dose: 0.25.

The original throughput FAIL remains preserved. The two journals are not pooled.

| Rubric | Contrast | Complete-pair estimate | Conservative 95% interval | Missing pairs |
|---|---|---:|---|---:|
| Second rubric | Target | 0.104 | [-0.098, 0.298] | 0 |
| Second rubric | Control1 | -0.188 | [-0.496, 0.169] | 0 |
| Second rubric | Control2 | -0.125 | [-0.463, 0.244] | 0 |
| Second rubric | Control3 | -0.031 | [-0.363, 0.309] | 0 |
| Second rubric | Specificity | 0.219 | [-0.448, 0.834] | see component panels |
| Paper rubric | Target | -0.052 | [-0.201, 0.101] | 0 |
| Paper rubric | Control1 | -0.094 | [-0.374, 0.212] | 0 |
| Paper rubric | Control2 | -0.094 | [-0.347, 0.187] | 0 |
| Paper rubric | Control3 | -0.125 | [-0.410, 0.193] | 0 |
| Paper rubric | Specificity | 0.052 | [-0.486, 0.559] | see component panels |

Second rubric frozen verdict: `positive_0.30_signature_excluded_at_selected_dose`.
Paper rubric frozen verdict: `positive_0.30_signature_excluded_at_selected_dose`.

Lifecycle: closed.
New compute upper bound: $16.88805826078038055555555556; carried prior bound: $16.565997654316512; cumulative: $33.45405591509689255555555556. Controller upper bounds, not provider invoices.

Second rubric is the frozen notebook-primary endpoint; Paper rubric is secondary. Primary intervals use paired blocks and worst-case missing labels. The three control panels are fixed, with 32 blocks each; their displayed intervals are descriptive, not simultaneous. Calibration quality and main quality are separate. Labels are not ground truth or consciousness evidence.

## Figure Captions

**main_contrasts.** Fixed-dose paired contrasts. Dots are complete-pair estimates; lines are individual 95% conservative paired-discordance CP bounds with worst-case missing labels. Target n=96 paired blocks; each fixed control panel n=32. The last row subtracts the equal mean of the three control gaps. Dashed +0.30 is the target threshold only. Control-panel comparisons are descriptive; intervals are not simultaneous across contrasts or rubrics. Quality status and frozen verdicts are reported separately.

**main_rates.** Fixed-dose label rates. Dots are positive/nonmissing labels; lines are missingness-aware marginal 95% CP limits. Negative (-) and positive (+) denote edit signs. The same 96 blocks supply the five arms, so cells are not independent samples; pairing enters the contrast analysis.

**calibration_rates.** Original calibration label rates. Dots are positive/nonmissing labels; whiskers are missingness-aware marginal 95% CP limits. These 204 original trials are separate from the 480 main trials. Target n=12 per dose/sign cell; each fixed control panel n=4. Dose 0.25 was quality-selected, not label-optimized. The original throughput FAIL is preserved unchanged.

**calibration_quality.** Original calibration quality diagnostics. Frozen heuristic flags are not human coherence validation; NLL pools both turns. Induction caps are exposure metadata; final caps remain quality failures. Fixed control panels remain separate. These are observed-sample summaries, not population estimates; no uncertainty calculation was frozen for these diagnostics.

**main_quality.** Fixed-dose main quality diagnostics, using only retrieved, scientifically auditable rows; the report states whether the main sample is complete. Frozen heuristic flags are not human coherence validation; NLL pools both turns. Induction caps are exposure metadata; final caps remain quality failures. Fixed control panels remain separate. These are observed-sample summaries, not population estimates; no uncertainty calculation was frozen for these diagnostics.

