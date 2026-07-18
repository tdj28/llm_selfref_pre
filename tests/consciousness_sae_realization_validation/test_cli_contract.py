from __future__ import annotations

import inspect
import unittest

from experiments.consciousness_sae_realization_validation import gate_receipts
from experiments.consciousness_sae_realization_validation import analysis
from experiments.consciousness_sae_realization_validation import guest_launcher
from experiments.consciousness_sae_realization_validation import runner


def _subparser(parser, name: str):
    subparser_actions = [
        action for action in parser._actions if hasattr(action, "choices") and action.choices
    ]
    if len(subparser_actions) != 1:
        raise AssertionError("expected exactly one subparser action")
    return subparser_actions[0].choices[name]


def _required_long_options(parser) -> set[str]:
    return {
        option
        for action in parser._actions
        if action.required
        for option in action.option_strings
        if option.startswith("--")
    }


class RunnerParserContractTests(unittest.TestCase):
    COMMON_REQUIRED = {
        "--plan-dir",
        "--volume-root",
        "--volume-id",
        "--run-id",
        "--model-snapshot",
        "--sae-path",
        "--j-lens-path",
        "--hourly-price-usd",
        "--campaign-started-at-unix",
        "--provider-terminate-at-unix",
        "--ownership-receipt",
        "--guest-receipt",
        "--cache-receipt",
        "--storage-budget",
    }

    def test_stage_a_requires_every_execution_and_provider_binding(self) -> None:
        stage_a = _subparser(runner.build_parser(), "stage-a")
        self.assertEqual(
            _required_long_options(stage_a),
            self.COMMON_REQUIRED
            | {"--preexecution-authorization", "--smoke-receipt"},
        )

    def test_stage_b_additionally_requires_the_full_gate_chain(self) -> None:
        stage_b = _subparser(runner.build_parser(), "stage-b")
        self.assertEqual(
            _required_long_options(stage_b),
            self.COMMON_REQUIRED
            | {
                "--stage-a-receipt",
                "--stage-a-audit",
                "--stage-b-permit",
                "--target-blind-receipt",
                "--preexecution-authorization",
            },
        )

    def test_volume_initialization_has_no_execution_bypass_arguments(self) -> None:
        init = _subparser(runner.build_parser(), "init-volume")
        self.assertEqual(
            _required_long_options(init), {"--volume-root", "--volume-id"}
        )

    def test_stage_a_authorization_and_orientation_precede_prompt_render(self) -> None:
        source = inspect.getsource(runner.execute_stage_a)
        self.assertLess(
            source.index("_validate_stage_a_stopship_chain("),
            source.index("_load_backend("),
        )
        self.assertLess(
            source.index("j_orientation.execute_orientation_rows("),
            source.index("_prompt_receipt(tokenizer, prompt_id)"),
        )
        stage_b_source = inspect.getsource(runner.execute_stage_b)
        self.assertLess(
            stage_b_source.index("_validate_stage_b_authorization("),
            stage_b_source.index("RawTransaction("),
        )
        self.assertLess(
            stage_b_source.index("_validate_stage_b_authorization("),
            stage_b_source.index("_load_backend("),
        )

    def test_every_guest_doc_command_disables_bytecode_writes(self) -> None:
        reproducing = (
            runner.REPO_ROOT
            / "docs/consciousness_sae_realization_validation/REPRODUCING.md"
        ).read_text(encoding="utf-8")
        for module in (
            "runpod_preflight",
            "storage_benchmark",
            "runner",
            "gate_receipts",
            "audit",
            "analysis",
        ):
            unsafe = (
                "python -m experiments.consciousness_sae_realization_validation."
                + module
            )
            self.assertNotIn(unsafe, reproducing)
        smoke = (
            runner.REPO_ROOT
            / "docs/consciousness_sae_realization_validation/SMOKE_TEST.md"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "python3 -B -u -m "
            "experiments.consciousness_sae_realization_validation.guest_launcher",
            smoke,
        )
        self.assertNotIn(
            "experiments.consciousness_sae_realization_validation.smoke_test \\",
            smoke,
        )

    def test_gpu_commands_are_allowlisted_behind_one_ownership_launcher(self) -> None:
        parser = guest_launcher.build_parser()
        self.assertEqual(_required_long_options(parser), {"--ownership-receipt"})
        action = next(
            action
            for action in parser._actions
            if hasattr(action, "choices") and action.choices
        )
        self.assertEqual(set(action.choices), {"smoke", "stage-a", "stage-b"})
        reproducing = (
            runner.REPO_ROOT
            / "docs/consciousness_sae_realization_validation/REPRODUCING.md"
        ).read_text(encoding="utf-8")
        self.assertNotIn(
            "consciousness_sae_realization_validation.runner stage-a",
            reproducing,
        )
        self.assertNotIn(
            "consciousness_sae_realization_validation.runner stage-b",
            reproducing,
        )


class ReceiptParserContractTests(unittest.TestCase):
    def test_stage_b_analysis_requires_same_authorization_and_plan(self) -> None:
        parser = _subparser(analysis.build_parser(), "stage-b")
        self.assertIn("--plan-dir", _required_long_options(parser))
        self.assertIn(
            "--preexecution-authorization", _required_long_options(parser)
        )

    def test_target_blind_builder_requires_executed_evidence(self) -> None:
        parser = _subparser(gate_receipts.build_parser(), "target-blind")
        self.assertEqual(
            _required_long_options(parser),
            {
                "--plan-manifest",
                "--stage-a-raw-receipt",
                "--stage-a-receipt",
                "--benchmark-receipt",
                "--storage-budget",
                "--output",
            },
        )

    def test_stage_b_permit_requires_freeze_review_and_gate_evidence(self) -> None:
        parser = _subparser(gate_receipts.build_parser(), "stage-b-permit")
        self.assertEqual(
            _required_long_options(parser),
            {
                "--plan-manifest",
                "--stage-a-receipt",
                "--target-blind-receipt",
                "--storage-budget",
                "--review-adjudication",
                "--plan-dir",
                "--source-inventory",
                "--remote-ref",
                "--run-id",
                "--spend-ceiling-usd",
                "--walltime-ceiling-seconds",
                "--output",
            },
        )


if __name__ == "__main__":
    unittest.main()
