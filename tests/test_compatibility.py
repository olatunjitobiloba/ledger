import importlib
import subprocess
import sys
import unittest


LEGACY_MODULES = (
    "day3",
    "day4",
    "day5",
    "day6",
    "day7",
    "day8",
    "day9",
    "day11",
    "day12",
    "day13",
    "day14",
    "day15",
    "day16",
    "day17",
    "day18",
    "day19",
    "day20",
    "day21",
    "day22",
)


class CompatibilityTests(unittest.TestCase):
    def test_legacy_modules_import(self) -> None:
        for name in LEGACY_MODULES:
            with self.subTest(module=name):
                self.assertIsNotNone(importlib.import_module(name))

    def test_descriptive_facades_import(self) -> None:
        from ledger.evaluation.evidence import export_reservation, restore_bundle
        from ledger.evaluation.reconciliation import reconcile
        from ledger.observability.api import app
        from ledger.observability.sdk import Ledger

        for symbol in (export_reservation, restore_bundle, reconcile, app, Ledger):
            self.assertIsNotNone(symbol)

    def test_legacy_help_commands(self) -> None:
        for module in LEGACY_MODULES:
            with self.subTest(module=module):
                result = subprocess.run(
                    [sys.executable, f"{module}.py", "--help"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0)
                self.assertTrue(result.stdout or result.stderr)


if __name__ == "__main__":
    unittest.main()
