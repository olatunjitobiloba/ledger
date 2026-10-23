import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from ledger import cli


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def run_cli(
    *args: str, cwd: Path | None = None, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ledger", *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
    )


class LedgerCliTests(unittest.TestCase):
    def test_help_lists_product_commands(self) -> None:
        result = run_cli("--help")

        self.assertEqual(result.returncode, 0)
        for command in ("doctor", "serve", "worker", "evidence"):
            self.assertIn(command, result.stdout)

    def test_doctor_help_is_read_only(self) -> None:
        result = run_cli("doctor", "--help")

        self.assertEqual(result.returncode, 0)
        self.assertIn("read-only", result.stdout.lower())

    def test_evidence_parser_requires_arguments(self) -> None:
        result = run_cli("evidence", "export")

        self.assertNotEqual(result.returncode, 0)

    def test_doctor_offline_checks(self) -> None:
        result = run_cli("doctor")

        self.assertIn(result.returncode, (0, 1))
        self.assertNotIn("sk-", result.stdout + result.stderr)
        self.assertNotIn("postgresql://", result.stdout + result.stderr)

    def test_malformed_dotenv_secret_is_not_exposed_by_help_or_doctor(self) -> None:
        secret_prefix = "sk-SEC"
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            shutil.copytree(REPOSITORY_ROOT / "ledger", workspace / "ledger")
            for filename in ("day4.py", "day22.py", "judge.py", "judge_groq.py"):
                shutil.copy2(REPOSITORY_ROOT / filename, workspace / filename)
            (workspace / ".env").write_text(
                "sk-SECRET-DO-NOT-PRINT\n", encoding="utf-8"
            )
            environment = os.environ.copy()
            inherited_path = environment.get("PYTHONPATH", "")
            environment["PYTHONPATH"] = os.pathsep.join(
                filter(None, (str(REPOSITORY_ROOT), inherited_path))
            )

            for arguments in (("--help",), ("doctor",), ("doctor", "--check-database")):
                with self.subTest(arguments=arguments):
                    result = run_cli(*arguments, cwd=workspace, env=environment)
                    self.assertNotIn(secret_prefix, result.stdout + result.stderr)

    def test_evidence_export_dispatches_parsed_arguments(self) -> None:
        reservation = uuid.UUID("11111111-1111-4111-8111-111111111111")
        output = Path("bundle.zip")

        with patch("ledger.cli.export_reservation", return_value=7) as export:
            result = cli.main(
                ["evidence", "export", "--reservation", str(reservation), "--output", str(output)]
            )

        self.assertEqual(result, 7)
        delegated = export.call_args.args[0]
        self.assertEqual(delegated.reservation, reservation)
        self.assertEqual(delegated.output, output)

    def test_evidence_restore_dispatches_parsed_arguments(self) -> None:
        bundle = Path("bundle.zip")

        with patch("ledger.cli.restore_bundle", return_value=3) as restore:
            result = cli.main(["evidence", "restore", "--bundle", str(bundle)])

        self.assertEqual(result, 3)
        self.assertEqual(restore.call_args.args[0].bundle, bundle)

    def test_serve_and_worker_dispatch_without_starting_services(self) -> None:
        with patch("ledger.cli._serve", return_value=None) as serve:
            self.assertEqual(cli.main(["serve"]), 0)
        with patch("ledger.cli.worker_main", return_value=None) as worker:
            self.assertEqual(cli.main(["worker"]), 0)

        serve.assert_called_once_with()
        worker.assert_called_once_with()

    def test_database_check_closes_connection_without_writing(self) -> None:
        connection = unittest.mock.MagicMock()
        connection.__enter__.return_value = connection

        with patch("day4.connect", return_value=connection) as connect:
            result = cli.run_doctor(check_database=True)

        self.assertIn(result, (0, 1))
        connect.assert_called_once_with()
        connection.__enter__.assert_called_once_with()
        connection.__exit__.assert_called_once()


if __name__ == "__main__":
    unittest.main()
