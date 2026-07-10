PYTHON ?= $(if $(wildcard venv/bin/python),venv/bin/python,steering/.venv/bin/python)
LATEXMK ?= latexmk
RELEASE_DIR := data/causal_transplant/confirmatory_v1_20260709

.PHONY: test compile paper audit public-audit verify

test:
	$(PYTHON) -m unittest discover -s tests -v

compile:
	$(PYTHON) -m py_compile \
		experiments/causal_transplant/analyze_causal_transplant.py \
		experiments/causal_transplant/run_causal_transplant.py \
		experiments/causal_transplant/judge_causal_outputs.py \
		experiments/causal_transplant/build_human_annotation_packet.py \
		experiments/causal_transplant/analyze_human_annotations.py \
		experiments/causal_transplant/assess_human_annotation_gate.py \
		experiments/causal_transplant/audit_headline_point_estimates.py \
		experiments/causal_transplant/build_release_manifest.py \
		experiments/exp2_sae/public_sae_protocol.py \
		experiments/exp2_sae/public_sae_consciousness_gating.py \
		experiments/exp2_sae/build_public_sae_consciousness_plan.py \
		experiments/exp2_sae/validate_public_sae_consciousness_plan.py \
		experiments/exp2_sae/audit_public_sae_consciousness_calibration.py \
		experiments/exp2_sae/run_public_sae_consciousness_gating.py \
		experiments/exp2_sae/build_public_sae_gating_judge_packet.py \
		experiments/exp2_sae/judge_public_sae_gating_local.py \
		experiments/exp2_sae/judge_public_sae_gating_external.py \
		experiments/exp2_sae/analyze_public_sae_consciousness_gating.py \
		experiments/exp2_sae/audit_public_sae_consciousness_headlines.py \
		experiments/exp2_sae/figure_public_sae_consciousness_gating.py \
		experiments/exp2_sae/build_public_sae_consciousness_release.py \
		experiments/exp2_sae/build_sae_construct_validity_extension.py \
		experiments/exp2_sae/analyze_sae_construct_validity_extension.py \
		experiments/exp2_sae/audit_sae_construct_validity_extension.py \
		experiments/exp2_sae/run_public_sae_placebo_steering.py \
		experiments/exp2_sae/run_public_sae_branched_specificity.py \
		experiments/exp2_sae/judge_public_sae_branched_specificity.py \
		experiments/exp2_sae/analyze_public_sae_branched_specificity.py \
		experiments/exp2_sae/analyze_public_sae_mapping_template_robustness.py \
		experiments/exp2_sae/audit_public_sae_branched_headlines.py \
		experiments/exp2_sae/audit_public_sae_mapping_headlines.py \
		experiments/exp2_sae/audit_public_sae_powered_headlines.py \
		experiments/exp2_sae/analyze_public_sae_placebo_steering.py \
		experiments/exp2_sae/judge_public_sae_results.py \
		experiments/exp2_sae/analyze_public_sae_two_turn.py \
		experiments/exp2_sae/compare_public_sae_token_caps.py \
		experiments/exp2_sae/merge_public_sae_runs.py \
		scripts/audit_public_release.py

paper:
	cd paper && $(LATEXMK) -pdf -halt-on-error -interaction=nonstopmode main.tex

audit:
	$(PYTHON) experiments/causal_transplant/audit_headline_point_estimates.py $(RELEASE_DIR)
	$(PYTHON) experiments/exp2_sae/audit_public_sae_mapping_headlines.py \
		data/public_sae_feature_maps/70b_balanced_80_20260709
	$(PYTHON) experiments/exp2_sae/analyze_public_sae_mapping_template_robustness.py \
		data/public_sae_feature_maps/70b_balanced_80_20260709
	$(PYTHON) experiments/exp2_sae/analyze_sae_construct_validity_extension.py \
		data/public_sae_feature_maps/70b_construct_validity_extension_20260710
	$(PYTHON) experiments/exp2_sae/audit_sae_construct_validity_extension.py \
		data/public_sae_feature_maps/70b_construct_validity_extension_20260710
	$(PYTHON) experiments/exp2_sae/audit_public_sae_powered_headlines.py \
		data/public_sae_placebo_steering/70b_two_turn_powered_n20_20260709
	$(PYTHON) experiments/exp2_sae/analyze_public_sae_branched_specificity.py \
		data/public_sae_placebo_steering/70b_branched_specificity_20260710
	$(PYTHON) experiments/exp2_sae/audit_public_sae_branched_headlines.py \
		data/public_sae_placebo_steering/70b_branched_specificity_20260710
	$(PYTHON) experiments/causal_transplant/build_release_manifest.py $(RELEASE_DIR)

public-audit:
	$(PYTHON) scripts/audit_public_release.py

verify: public-audit test compile paper
	git diff --check
