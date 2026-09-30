PYTHON ?= $(if $(wildcard venv/bin/python),venv/bin/python,python3)
LATEXMK ?= latexmk

.PHONY: test compile paper audit public-audit verify

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

# Recompute on copies, never on frozen releases.
audit:
	$(PYTHON) scripts/check_frozen_audits.py --extended

public-audit:
	$(PYTHON) scripts/audit_public_release.py

verify: public-audit test compile paper
	git diff --check
