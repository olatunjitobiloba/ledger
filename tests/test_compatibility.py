import importlib
import subprocess
import sys
import unittest


PIPELINE_MODULES = (
    "ledger.pipeline.golden_set",
    "ledger.pipeline.evaluation_runs",
    "ledger.pipeline.costs",
    "ledger.pipeline.regression",
    "ledger.pipeline.prompt_evaluation",
    "ledger.pipeline.injection_scan",
    "ledger.pipeline.release_policy",
    "ledger.pipeline.provenance",
    "ledger.pipeline.runtime_binding",
    "ledger.pipeline.container_binding",
    "ledger.pipeline.orchestration",
    "ledger.pipeline.preflight",
    "ledger.pipeline.spend_plan",
    "ledger.pipeline.cost_reconciliation",
    "ledger.pipeline.spend_reservations",
    "ledger.pipeline.reservation_recovery",
    "ledger.pipeline.execution_context",
    "ledger.pipeline.reservation_reconciliation",
    "ledger.pipeline.evidence_bundle",
)


class CompatibilityTests(unittest.TestCase):
    def test_pipeline_modules_import(self) -> None:
        for name in PIPELINE_MODULES:
            with self.subTest(module=name):
                self.assertIsNotNone(importlib.import_module(name))

    def test_descriptive_facades_import(self) -> None:
        from ledger.evaluation.evidence import export_reservation, restore_bundle
        from ledger.evaluation.reconciliation import reconcile
        from ledger.observability.api import app
        from ledger.observability.sdk import Ledger

        for symbol in (export_reservation, restore_bundle, reconcile, app, Ledger):
            self.assertIsNotNone(symbol)

    def test_module_help_commands(self) -> None:
        for module in PIPELINE_MODULES:
            with self.subTest(module=module):
                result = subprocess.run(
                    [sys.executable, "-m", module, "--help"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0)
                self.assertTrue(result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
