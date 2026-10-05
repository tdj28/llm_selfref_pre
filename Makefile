PYTHON ?= $(if $(wildcard venv/bin/python),venv/bin/python,python3)
LATEXMK ?= latexmk

.PHONY: test compile paper paper-verify arxiv audit public-audit verify

test:
	$(PYTHON) -m pytest tests

compile:
	$(PYTHON) scripts/check_python_sources.py
	bash -n experiments/exp2_sae/run_gemma_scope_9b_stage2.sh
	bash -n experiments/exp2_sae/run_gemma_scope_9b_external_controller.sh
	bash -n experiments/exp2_sae/run_sae_jlens_runpod.sh
	bash -n experiments/exp2_sae/run_sae_jlens_v2_calibration_runpod.sh
	bash -n experiments/exp2_sae/run_sae_jlens_v2_runpod.sh

paper:
	cd paper && $(LATEXMK) -pdf -halt-on-error -interaction=nonstopmode main.tex

# Self-contained arXiv source bundle, plain-text abstract and standalone build.
arxiv: paper
	$(PYTHON) scripts/build_arxiv_bundle.py

# Read-only checks of the current manuscript and its packaged evidence.
paper-verify:
	$(PYTHON) scripts/verify_evidence.py
	$(PYTHON) scripts/verify_figure_values.py
	$(PYTHON) scripts/verify_figure_presentation.py
	$(PYTHON) scripts/verify_rubric_audit.py
	$(PYTHON) scripts/verify_source_alignment.py
	$(PYTHON) scripts/verify_source_jlens_table.py
	$(PYTHON) scripts/verify_ensemble_alignment.py
	$(PYTHON) scripts/verify_steering_dose.py
	$(PYTHON) scripts/verify_steering_truncation.py
	$(PYTHON) scripts/verify_dose_followup.py --require-pinned
	$(PYTHON) scripts/verify_feature_map_table.py
	$(PYTHON) scripts/verify_swap_cells.py
	$(PYTHON) scripts/verify_fidelity_calibration.py
	$(PYTHON) scripts/verify_reporting_bound.py
	$(PYTHON) scripts/verify_completed_extensions.py
	$(PYTHON) scripts/verify_model_panel_extension.py --check
	$(PYTHON) scripts/verify_qwen_extension.py --check --require-pinned
	$(PYTHON) scripts/verify_repeated_extension.py --release data/repeated_swap/completed_v1_20261005 --publication evidence/repeated_extension --release-manifest-sha256 c0d44ab369739425645475ef1e62281c7615982c5288b6d0cc4a0b2ba36c75cf --publication-manifest-sha256 b2cd569022042097cf574f2dd7038cad20489a6b43992eeb01f631357ff5e242 --binding evidence/repeated_extension_row_binding.json --paper --require-pinned
	$(PYTHON) scripts/uncertainty_sensitivity.py --check
	$(PYTHON) -B reviews/reproducibility/run.py --verify-only

# Recompute on copies, never on frozen releases.
audit:
	$(PYTHON) scripts/check_frozen_audits.py --extended

public-audit:
	$(PYTHON) scripts/audit_public_release.py

verify: public-audit test compile paper-verify paper
	git diff --check

# verify.yml is a frozen frontier-study input. Prepare its current jobs here
# without rewriting that workflow or adding network actions to local checks.
ifeq ($(GITHUB_ACTIONS),true)
.PHONY: ci-test-environment ci-paper-environment
test: | ci-test-environment
paper-verify: | ci-paper-environment

ci-test-environment:
	$(PYTHON) scripts/prepare_ci_verification.py tests

ci-paper-environment:
	$(PYTHON) scripts/prepare_ci_verification.py paper
endif
