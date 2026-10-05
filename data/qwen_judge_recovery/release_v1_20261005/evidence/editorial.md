# Qwen3.8: post-hoc judgment repair

The repair recovered 3 of the three missing Astra structured judgments on Qwen3.8-2.4T-A95B. All 256 original answers, completed judgments and source pairs are unchanged. The three requests were selected after the original incomplete release because they had technical failures, not because of their labels.

The primary endpoint remains Astra's inclusive current-attribution label. Opus is the robustness judge; explicit-attribution and paper-rubric labels remain secondary. The analysis still uses 32 paired blocks and the original four-comparison family, including the unrun Mistral main panel.

SH-HS: the complete-case estimate changes from 0.400 (30/32 complete blocks) to 0.406 (32/32), with a familywise 95% interval of [-0.157, 0.969].

NS-NH: the complete-case estimate changes from 0.194 (31/32 complete blocks) to 0.188 (32/32), with a familywise 95% interval of [-0.376, 0.751].

Both primary intervals include zero. These estimates do not establish either contrast as a population effect; the neutral comparison is not an equivalence test.

Under Astra, SH-HS is 0.406 for inclusive attribution, 0.094 for explicit attribution and 0.156 under the paper rubric. These are different measurements of the same answers, not independent replications.

Under Opus, SH-HS is 0.438 for inclusive attribution, 0.094 for explicit attribution and 0.219 under the paper rubric. These are different measurements of the same answers, not independent replications.

SH-HS compares the two incongruent packages; it is a signed contrast, not proof of absolute instruction dominance. Same-condition donor controls do not eliminate instruction-continuation mismatch. These are automated labels, not validated measurements of experience.

New judgment cost is bounded by $0.22744425. The original $0.96522800 in unresolved charges remains carried forward. The original release is still recorded as incomplete; this is a separately timed scoring repair, not a new prospective replication. It concerns Qwen3.8, not the earlier Qwen3.5 companion study.
