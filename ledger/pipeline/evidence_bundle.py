"""Portable reservation evidence bundle primitives.

python -m ledger.pipeline.evidence_bundle test
python -m ledger.pipeline.evidence_bundle export --reservation RESERVATION_UUID --output PATH.zip
python -m ledger.pipeline.evidence_bundle restore --bundle PATH.zip
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import unittest
import uuid
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

from ledger.pipeline.evaluation_runs import connect
from ledger.pipeline.execution_context import validate_context
from ledger.pipeline.reservation_reconciliation import (
    require_finished_candidate,
    validate_association,
)
from ledger.pipeline.reservation_recovery import validate_candidate
from ledger.pipeline.spend_plan import canonical_hash

VERSION = "ledger-evidence-bundle-v1"
MEMBERS = {"manifest.json", "plan.json", "rehearsal.json"}
MAX_MEMBER_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def verify_member_hash(raw: bytes, expected: object) -> str:
    if not isinstance(expected, str) or len(expected) != 64:
        raise ValueError("Evidence hash is invalid.")
    actual = sha256(raw)
    if actual != expected or any(c not in "0123456789abcdef" for c in expected):
        raise ValueError("Evidence hash mismatch.")
    return actual


def validate_report_path(path: object, *, must_exist: bool) -> Path:
    if not isinstance(path, (str, Path)):
        raise ValueError("Report path is invalid.")
    supplied = Path(path)
    if supplied.is_absolute() or "\\" in str(path):
        raise ValueError("Report path must be a safe relative path.")

    parts = supplied.parts
    if len(parts) != 4 or parts[0] != "results" or parts[1] != "day14":
        raise ValueError("Report path is outside results/day14.")
    try:
        report_id = uuid.UUID(parts[2])
    except (ValueError, AttributeError):
        report_id = None
    if report_id is None or str(report_id) != parts[2]:
        raise ValueError("Report path must use a canonical UUID directory.")
    if supplied.name != "report.json":
        raise ValueError("Report path must end in report.json.")

    lexical = Path()
    for component in supplied.parts:
        lexical /= component
        if lexical.is_symlink():
            raise ValueError("Report path contains a symlink.")

    root = Path("results/day14").resolve()
    resolved = supplied.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Report path escaped results/day14.")
    if must_exist and (not resolved.is_file() or resolved.is_symlink()):
        raise ValueError("Report path is not a regular file.")
    return resolved


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_plan_bytes(plan: dict[str, Any]) -> bytes:
    if not isinstance(plan, dict):
        raise ValueError("Plan must be an object.")
    return json.dumps(
        plan, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def manifest_bytes(manifest: dict[str, Any]) -> bytes:
    if (
        not isinstance(manifest, dict)
        or manifest.get("version") != VERSION
        or manifest.get("signed") is not False
    ):
        raise ValueError("Evidence manifest is invalid.")
    return _canonical_json(manifest)


def build_archive(
    manifest: dict[str, Any], plan_bytes: bytes, rehearsal_bytes: bytes
) -> bytes:
    manifest_raw = manifest_bytes(manifest)
    members = {
        "manifest.json": manifest_raw,
        "plan.json": plan_bytes,
        "rehearsal.json": rehearsal_bytes,
    }
    if any(len(raw) > MAX_MEMBER_BYTES for raw in members.values()):
        raise ValueError("Evidence member exceeds size limit.")
    if verify_member_hash(plan_bytes, manifest.get("plan_sha256")) != sha256(
        plan_bytes
    ):
        raise ValueError("Plan hash does not match manifest.")
    if verify_member_hash(rehearsal_bytes, manifest.get("rehearsal_sha256")) != sha256(
        rehearsal_bytes
    ):
        raise ValueError("Rehearsal hash does not match manifest.")
    output = tempfile.SpooledTemporaryFile(max_size=MAX_ARCHIVE_BYTES)
    try:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name in ("manifest.json", "plan.json", "rehearsal.json"):
                archive.writestr(name, members[name])
        output.seek(0)
        raw = output.read()
    finally:
        output.close()
    if len(raw) > MAX_ARCHIVE_BYTES:
        raise ValueError("Evidence archive exceeds size limit.")
    with zipfile.ZipFile(__import__("io").BytesIO(raw)) as archive:
        if any(
            info.file_size > MAX_MEMBER_BYTES or info.compress_size > MAX_MEMBER_BYTES
            for info in archive.infolist()
        ):
            raise ValueError("Evidence member exceeds size limit.")
    return raw


def read_archive_from_bytes(
    archive_bytes: bytes,
) -> tuple[dict[str, Any], bytes, bytes]:
    if len(archive_bytes) > MAX_ARCHIVE_BYTES:
        raise ValueError("Evidence archive exceeds size limit.")
    try:
        archive = zipfile.ZipFile(__import__("io").BytesIO(archive_bytes))
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)) or set(names) != MEMBERS:
            raise ValueError("Evidence archive members are invalid.")
        raw_members: dict[str, bytes] = {}
        for info in infos:
            mode = (info.external_attr >> 16) & 0xFFFF
            if info.is_dir() or info.flag_bits & 0x1 or (mode & 0o170000) == 0o120000:
                raise ValueError("Directories and encrypted members are forbidden.")
            if (
                info.file_size > MAX_MEMBER_BYTES
                or info.compress_size > MAX_MEMBER_BYTES
            ):
                raise ValueError("Evidence member exceeds size limit.")
            raw_members[info.filename] = archive.read(info)
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        raise ValueError("Evidence archive is invalid.") from exc
    manifest = json.loads(raw_members["manifest.json"])
    if (
        not isinstance(manifest, dict)
        or manifest.get("version") != VERSION
        or manifest.get("signed") is not False
    ):
        raise ValueError("Evidence manifest is invalid.")
    plan_bytes = raw_members["plan.json"]
    plan = json.loads(plan_bytes)
    if not isinstance(plan, dict) or canonical_plan_bytes(plan) != plan_bytes:
        raise ValueError("Plan is not canonical JSON.")
    rehearsal_bytes = raw_members["rehearsal.json"]
    verify_member_hash(plan_bytes, manifest.get("plan_sha256"))
    verify_member_hash(rehearsal_bytes, manifest.get("rehearsal_sha256"))
    return manifest, plan_bytes, rehearsal_bytes


def read_archive(path: Path) -> tuple[dict[str, Any], bytes, bytes]:
    try:
        path = Path(path)
        if path.is_symlink() or not path.is_file():
            raise ValueError("Evidence archive path is not a regular file.")
        raw = path.read_bytes()
    except (OSError, ValueError) as exc:
        if isinstance(exc, ValueError):
            raise
        raise ValueError("Evidence archive input is unavailable.") from exc
    return read_archive_from_bytes(raw)


def publish_no_overwrite(path: Path, content: bytes) -> str:
    path = Path(path)
    parent_parts = path.parent.parts
    current = Path(path.parent.anchor) if path.parent.anchor else Path()
    if path.parent.anchor and parent_parts and parent_parts[0] == path.parent.anchor:
        parent_parts = parent_parts[1:]
    for component in parent_parts:
        current /= component
        if current.is_symlink():
            raise ValueError("Publication path contains a symlinked parent.")
        try:
            current.mkdir(exist_ok=True)
        except OSError as exc:
            raise ValueError("Publication parent is unavailable.") from exc
        if current.is_symlink() or not current.is_dir():
            raise ValueError("Publication parent is not a regular directory.")
    if path.exists() or path.is_symlink():
        if path.is_file() and not path.is_symlink() and path.read_bytes() == content:
            return "ALREADY_PRESENT"
        raise ValueError("Refusing to replace existing output.")
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if (
                path.is_file()
                and not path.is_symlink()
                and path.read_bytes() == content
            ):
                return "ALREADY_PRESENT"
            raise ValueError("Refusing to replace existing output.") from None
        return "PUBLISHED"
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def export_reservation(args: argparse.Namespace) -> int:
    with connect() as connection, connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        row = connection.execute(
            """
                SELECT state, plan, plan_sha256, candidate_run_id, exit_code,
                       rehearsal_report, rehearsal_report_sha256
                FROM ledger_spend_reservations
                WHERE reservation_id = %s
                """,
            (args.reservation,),
        ).fetchone()
        if row is None:
            raise ValueError("Reservation does not exist.")
        (
            state,
            plan,
            plan_hash,
            candidate,
            exit_code,
            rehearsal_path,
            rehearsal_hash,
        ) = row
        candidate_id = require_finished_candidate(state, candidate)
        if canonical_hash(plan) != plan_hash:
            raise ValueError("Stored plan and reservation hash disagree.")

        report_manifest_path = str(rehearsal_path)
        report_path = validate_report_path(rehearsal_path, must_exist=True)
        report_bytes = report_path.read_bytes()
        if sha256(report_bytes) != rehearsal_hash:
            raise ValueError("Saved rehearsal report hash differs from the ledger.")
        report = json.loads(report_bytes)
        if not isinstance(report, dict):
            raise ValueError("Saved rehearsal report is not an object.")
        validate_association(
            args.reservation,
            plan,
            plan_hash,
            candidate_id,
            exit_code,
            report,
        )

        candidate_row = connection.execute(
            """
                SELECT config, reviewed_by
                FROM ledger_eval_runs
                WHERE run_id = %s
                """,
            (candidate_id,),
        ).fetchone()
        if candidate_row is None:
            raise ValueError("Candidate run does not exist.")
        config, reviewed_by = candidate_row
        validate_context(
            config.get("execution_context") if isinstance(config, dict) else None,
            args.reservation,
            plan_hash,
        )
        validate_candidate(config, reviewed_by, plan)

    plan_bytes = canonical_plan_bytes(plan)
    manifest = {
        "version": VERSION,
        "signed": False,
        "reservation_id": str(args.reservation),
        "candidate_run_id": str(candidate_id),
        "plan_sha256": plan_hash,
        "rehearsal_report": report_manifest_path,
        "rehearsal_sha256": sha256(report_bytes),
    }
    archive_bytes = build_archive(manifest, plan_bytes, report_bytes)
    status = publish_no_overwrite(args.output, archive_bytes)
    print(f"Exported {args.output} ({status}).")
    return 0


def _canonical_uuid(value: object, label: str) -> uuid.UUID:
    if not isinstance(value, str):
        raise ValueError(f"{label} is invalid.")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise ValueError(f"{label} is invalid.") from None
    if str(parsed) != value:
        raise ValueError(f"{label} is not canonical.")
    return parsed


def restore_bundle(args: argparse.Namespace) -> int:
    manifest, plan_bytes, rehearsal_bytes = read_archive(args.bundle)
    reservation_id = _canonical_uuid(
        manifest.get("reservation_id"), "Manifest reservation ID"
    )
    bundled_candidate = _canonical_uuid(
        manifest.get("candidate_run_id"), "Manifest candidate ID"
    )
    plan = json.loads(plan_bytes)
    report = json.loads(rehearsal_bytes)
    if not isinstance(plan, dict):
        raise ValueError("Bundled plan is not an object.")
    if not isinstance(report, dict):
        raise ValueError("Bundled rehearsal report is not an object.")
    if canonical_plan_bytes(plan) != plan_bytes:
        raise ValueError("Plan is not canonical JSON.")
    plan_hash = verify_member_hash(plan_bytes, manifest.get("plan_sha256"))
    rehearsal_hash = verify_member_hash(
        rehearsal_bytes, manifest.get("rehearsal_sha256")
    )
    manifest_report = manifest.get("rehearsal_report")
    validate_report_path(manifest_report, must_exist=False)
    report_path = Path(manifest_report)
    parent_id = _canonical_uuid(report_path.parts[2], "Report parent ID")
    if report.get("rehearsal_id") != str(parent_id):
        raise ValueError("Rehearsal report ID differs from manifest path.")

    with connect() as connection, connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        row = connection.execute(
            """
                SELECT state, plan, plan_sha256, candidate_run_id, exit_code,
                       rehearsal_report, rehearsal_report_sha256
                FROM ledger_spend_reservations
                WHERE reservation_id = %s
                """,
            (reservation_id,),
        ).fetchone()
        if row is None:
            raise ValueError("Reservation does not exist.")
        (
            state,
            receiving_plan,
            receiving_plan_hash,
            receiving_candidate,
            exit_code,
            receiving_report_path,
            receiving_report_hash,
        ) = row
        finished_candidate = require_finished_candidate(state, receiving_candidate)
        if finished_candidate != bundled_candidate:
            raise ValueError("Receiving candidate differs from bundle.")
        if receiving_plan_hash != plan_hash or receiving_plan != plan:
            raise ValueError("Receiving plan differs from bundle.")
        if receiving_report_path != manifest_report:
            raise ValueError("Receiving report path differs from bundle.")
        if receiving_report_hash != rehearsal_hash:
            raise ValueError("Receiving report hash differs from bundle.")
        validate_association(
            reservation_id,
            plan,
            plan_hash,
            finished_candidate,
            exit_code,
            report,
        )

        candidate_row = connection.execute(
            """
                SELECT config, reviewed_by
                FROM ledger_eval_runs
                WHERE run_id = %s
                """,
            (finished_candidate,),
        ).fetchone()
        if candidate_row is None:
            raise ValueError("Candidate run does not exist.")
        config, reviewed_by = candidate_row
        if not isinstance(config, dict):
            raise ValueError("Candidate configuration is invalid.")
        validate_context(config.get("execution_context"), reservation_id, plan_hash)
        validate_candidate(config, reviewed_by, plan)

    trusted_path = validate_report_path(receiving_report_path, must_exist=False)
    status = publish_no_overwrite(trusted_path, rehearsal_bytes)
    print(f"Restored {trusted_path} ({status}).")
    return 0


class PortableEvidenceBundleTests(unittest.TestCase):
    def manifest(self, plan: bytes, rehearsal: bytes) -> dict[str, Any]:
        return {
            "version": VERSION,
            "signed": False,
            "plan_sha256": sha256(plan),
            "rehearsal_sha256": sha256(rehearsal),
        }

    def restore_fixture(
        self,
    ) -> tuple[dict[str, Any], bytes, bytes, uuid.UUID, uuid.UUID]:
        reservation_id = uuid.UUID("11111111-1111-4111-8111-111111111111")
        candidate_id = uuid.UUID("22222222-2222-4222-8222-222222222222")
        plan = canonical_plan_bytes({})
        rehearsal = _canonical_json({"rehearsal_id": str(candidate_id)})
        manifest = self.manifest(plan, rehearsal)
        manifest.update(
            {
                "reservation_id": str(reservation_id),
                "candidate_run_id": str(candidate_id),
                "rehearsal_report": (f"results/day14/{candidate_id}/report.json"),
            }
        )
        return manifest, plan, rehearsal, reservation_id, candidate_id

    def mock_restore_connection(
        self,
        reservation_row: tuple[Any, ...],
        candidate_row: tuple[Any, ...],
    ) -> MagicMock:
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.transaction.return_value.__enter__.return_value = connection

        def execute(query: str, _params: object = None) -> Mock:
            cursor = Mock()
            if "ledger_spend_reservations" in query:
                cursor.fetchone.return_value = reservation_row
            elif "ledger_eval_runs" in query:
                cursor.fetchone.return_value = candidate_row
            return cursor

        connection.execute.side_effect = execute
        return connection

    def write_restore_archive(
        self, directory: Path
    ) -> tuple[Path, dict[str, Any], bytes, bytes, uuid.UUID, uuid.UUID]:
        manifest, plan, rehearsal, reservation_id, candidate_id = self.restore_fixture()
        bundle = directory / "bundle.zip"
        bundle.write_bytes(build_archive(manifest, plan, rehearsal))
        return bundle, manifest, plan, rehearsal, reservation_id, candidate_id

    def restore_args(self, bundle: Path) -> argparse.Namespace:
        return argparse.Namespace(bundle=bundle)

    def test_accept_canonical_report_path(self):
        path = validate_report_path(
            "results/day14/11111111-1111-4111-8111-111111111111/report.json",
            must_exist=False,
        )
        self.assertEqual(path.name, "report.json")

    def test_reject_traversal(self):
        with self.assertRaises(ValueError):
            validate_report_path("results/day14/../report.json", must_exist=False)

    def test_reject_absolute_path(self):
        with self.assertRaises(ValueError):
            validate_report_path(str(Path.cwd() / "report.json"), must_exist=False)

    def test_reject_evidence_hash_mismatch(self):
        with self.assertRaises(ValueError):
            verify_member_hash(b"evidence", "0" * 64)

    def test_accept_matching_manifest_hashes(self):
        plan, rehearsal = b'{"a":1}', b"report"
        manifest, _, _ = read_archive_from_bytes(
            build_archive(self.manifest(plan, rehearsal), plan, rehearsal)
        )
        self.assertEqual(manifest["plan_sha256"], sha256(plan))

    def test_unicode_plan_matches_spend_plan_hash_and_round_trips(self):
        plan = {"payload": {"description": "Café — réservé"}}
        plan_bytes = canonical_plan_bytes(plan)
        self.assertEqual(canonical_hash(plan), sha256(plan_bytes))
        manifest = self.manifest(plan_bytes, b"report")
        read_manifest, read_plan_bytes, read_rehearsal = read_archive_from_bytes(
            build_archive(manifest, plan_bytes, b"report")
        )
        self.assertEqual(read_manifest["plan_sha256"], canonical_hash(plan))
        self.assertEqual(read_plan_bytes, plan_bytes)
        self.assertEqual(read_rehearsal, b"report")

    def test_reject_compressed_member_over_size_limit(self):
        archive_bytes = build_archive(
            self.manifest(b'{"a":1}', b"report"), b'{"a":1}', b"report"
        )
        with zipfile.ZipFile(__import__("io").BytesIO(archive_bytes)) as archive:
            infos = archive.infolist()
        infos[0].compress_size = MAX_MEMBER_BYTES + 1
        with patch.object(zipfile.ZipFile, "infolist", return_value=infos):
            with self.assertRaises(ValueError):
                read_archive_from_bytes(archive_bytes)

    def test_builder_rejects_compressed_member_over_size_limit(self):
        plan, rehearsal = b'{"a":1}', b"report"
        manifest = self.manifest(plan, rehearsal)
        archive_bytes = build_archive(manifest, plan, rehearsal)
        with zipfile.ZipFile(__import__("io").BytesIO(archive_bytes)) as archive:
            infos = archive.infolist()
        infos[1].compress_size = MAX_MEMBER_BYTES + 1
        with patch.object(zipfile.ZipFile, "infolist", return_value=infos):
            with self.assertRaises(ValueError):
                build_archive(manifest, plan, rehearsal)

    def test_reuse_identical_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bundle.zip"
            path.write_bytes(b"same")
            self.assertEqual(publish_no_overwrite(path, b"same"), "ALREADY_PRESENT")

    def test_reject_different_existing_output_without_changing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bundle.zip"
            path.write_bytes(b"original")
            with self.assertRaises(ValueError):
                publish_no_overwrite(path, b"different")
            self.assertEqual(path.read_bytes(), b"original")

    def test_reject_unexpected_archive_member(self):
        output = __import__("io").BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            for name in ("manifest.json", "plan.json", "rehearsal.json", "extra"):
                archive.writestr(name, b"{}")
        with self.assertRaises(ValueError):
            read_archive_from_bytes(output.getvalue())

    def test_reject_symlinked_report_roots(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path.cwd()
            workspace = Path(directory)
            try:
                os.chdir(workspace)
                target = workspace / "real-results"
                (target / "day14").mkdir(parents=True)
                try:
                    os.symlink(target, workspace / "results", target_is_directory=True)
                except OSError:
                    self.skipTest("symlinks are unavailable")
                with self.assertRaises(ValueError):
                    validate_report_path(
                        "results/day14/11111111-1111-4111-8111-111111111111/report.json",
                        must_exist=False,
                    )
            finally:
                os.chdir(original)

        with tempfile.TemporaryDirectory() as directory:
            original = Path.cwd()
            workspace = Path(directory)
            try:
                os.chdir(workspace)
                (workspace / "results").mkdir()
                target = workspace / "real-day14"
                target.mkdir()
                try:
                    os.symlink(
                        target,
                        workspace / "results" / "day14",
                        target_is_directory=True,
                    )
                except OSError:
                    self.skipTest("symlinks are unavailable")
                with self.assertRaises(ValueError):
                    validate_report_path(
                        "results/day14/11111111-1111-4111-8111-111111111111/report.json",
                        must_exist=False,
                    )
            finally:
                os.chdir(original)

    def test_reject_symlinked_publication_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            target = workspace / "target"
            target.mkdir()
            try:
                os.symlink(target, workspace / "published", target_is_directory=True)
            except OSError:
                self.skipTest("symlinks are unavailable")
            with self.assertRaises(ValueError):
                publish_no_overwrite(workspace / "published" / "bundle.zip", b"data")

    def test_read_archive_rejects_unsafe_input(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            with self.assertRaises(ValueError):
                read_archive(workspace / "missing.zip")
            workspace.mkdir(exist_ok=True)
            with self.assertRaises(ValueError):
                read_archive(workspace)

    def test_manifest_version_is_required(self):
        plan, rehearsal = b'{"a":1}', b"report"
        manifest = self.manifest(plan, rehearsal)
        manifest["version"] = "wrong"
        with self.assertRaises(ValueError):
            build_archive(manifest, plan, rehearsal)

        archive = build_archive(self.manifest(plan, rehearsal), plan, rehearsal)
        output = __import__("io").BytesIO()
        with zipfile.ZipFile(output, "w") as rewritten:
            for name in ("manifest.json", "plan.json", "rehearsal.json"):
                raw = (
                    json.dumps(
                        {
                            "version": "wrong",
                            "signed": False,
                            "plan_sha256": sha256(plan),
                            "rehearsal_sha256": sha256(rehearsal),
                        }
                    ).encode()
                    if name == "manifest.json"
                    else {"plan.json": plan, "rehearsal.json": rehearsal}[name]
                )
                rewritten.writestr(name, raw)
        self.assertNotEqual(archive, output.getvalue())
        with self.assertRaises(ValueError):
            read_archive_from_bytes(output.getvalue())

    def test_restore_rejects_malformed_archive_before_connecting(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "malformed.zip"
            bundle.write_bytes(b"not a zip archive")
            with patch(__name__ + ".connect") as connect_mock:
                with self.assertRaises(ValueError):
                    restore_bundle(self.restore_args(bundle))
            connect_mock.assert_not_called()

    def test_restore_rejects_receiving_candidate_mismatch_without_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path.cwd()
            os.chdir(directory)
            try:
                bundle, manifest, plan, rehearsal, _reservation_id, _candidate_id = (
                    self.write_restore_archive(Path(directory))
                )
                receiving_row = (
                    "FINISHED",
                    json.loads(plan),
                    sha256(plan),
                    uuid.UUID("33333333-3333-4333-8333-333333333333"),
                    0,
                    manifest["rehearsal_report"],
                    sha256(rehearsal),
                )
                connection = self.mock_restore_connection(
                    receiving_row, ({}, "reviewer")
                )
                with (
                    patch(__name__ + ".connect", return_value=connection),
                    patch(__name__ + ".validate_association"),
                    patch(__name__ + ".validate_context"),
                    patch(__name__ + ".validate_candidate"),
                ):
                    with self.assertRaises(ValueError):
                        restore_bundle(self.restore_args(bundle))
                self.assertFalse(Path(manifest["rehearsal_report"]).exists())
            finally:
                os.chdir(original)

    def test_restore_publishes_exact_report_bytes_to_trusted_path(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path.cwd()
            os.chdir(directory)
            try:
                bundle, manifest, plan, rehearsal, _reservation_id, candidate_id = (
                    self.write_restore_archive(Path(directory))
                )
                receiving_row = (
                    "FINISHED",
                    json.loads(plan),
                    sha256(plan),
                    candidate_id,
                    0,
                    manifest["rehearsal_report"],
                    sha256(rehearsal),
                )
                connection = self.mock_restore_connection(
                    receiving_row, ({}, "reviewer")
                )
                with (
                    patch(__name__ + ".connect", return_value=connection),
                    patch(__name__ + ".validate_association"),
                    patch(__name__ + ".validate_context"),
                    patch(__name__ + ".validate_candidate"),
                ):
                    self.assertEqual(restore_bundle(self.restore_args(bundle)), 0)
                self.assertEqual(
                    Path(manifest["rehearsal_report"]).read_bytes(), rehearsal
                )
            finally:
                os.chdir(original)

    def test_restore_reports_already_present_for_identical_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path.cwd()
            os.chdir(directory)
            try:
                bundle, manifest, plan, rehearsal, _reservation_id, candidate_id = (
                    self.write_restore_archive(Path(directory))
                )
                trusted = Path(manifest["rehearsal_report"])
                trusted.parent.mkdir(parents=True)
                trusted.write_bytes(rehearsal)
                receiving_row = (
                    "FINISHED",
                    json.loads(plan),
                    sha256(plan),
                    candidate_id,
                    0,
                    manifest["rehearsal_report"],
                    sha256(rehearsal),
                )
                connection = self.mock_restore_connection(
                    receiving_row, ({}, "reviewer")
                )
                with (
                    patch(__name__ + ".connect", return_value=connection),
                    patch(__name__ + ".validate_association"),
                    patch(__name__ + ".validate_context"),
                    patch(__name__ + ".validate_candidate"),
                    patch("builtins.print") as print_mock,
                ):
                    self.assertEqual(restore_bundle(self.restore_args(bundle)), 0)
                self.assertIn("ALREADY_PRESENT", print_mock.call_args.args[0])
            finally:
                os.chdir(original)

    def test_restore_rejects_conflicting_existing_evidence_without_replacing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path.cwd()
            os.chdir(directory)
            try:
                bundle, manifest, plan, rehearsal, _reservation_id, candidate_id = (
                    self.write_restore_archive(Path(directory))
                )
                trusted = Path(manifest["rehearsal_report"])
                trusted.parent.mkdir(parents=True)
                trusted.write_bytes(b"existing evidence")
                receiving_row = (
                    "FINISHED",
                    json.loads(plan),
                    sha256(plan),
                    candidate_id,
                    0,
                    manifest["rehearsal_report"],
                    sha256(rehearsal),
                )
                connection = self.mock_restore_connection(
                    receiving_row, ({}, "reviewer")
                )
                with (
                    patch(__name__ + ".connect", return_value=connection),
                    patch(__name__ + ".validate_association"),
                    patch(__name__ + ".validate_context"),
                    patch(__name__ + ".validate_candidate"),
                ):
                    with self.assertRaises(ValueError):
                        restore_bundle(self.restore_args(bundle))
                self.assertEqual(trusted.read_bytes(), b"existing evidence")
            finally:
                os.chdir(original)


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("test")
    export = subparsers.add_parser("export")
    export.add_argument("--reservation", required=True, type=uuid.UUID)
    export.add_argument("--output", required=True, type=Path)
    restore = subparsers.add_parser("restore")
    restore.add_argument("--bundle", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "test":
        result = unittest.main(
            argv=[sys.argv[0], "PortableEvidenceBundleTests"], exit=False
        )
        return 0 if result.result.wasSuccessful() else 1
    if args.command == "export":
        return export_reservation(args)
    if args.command == "restore":
        return restore_bundle(args)
    raise SystemExit("Unknown command.")


if __name__ == "__main__":
    raise SystemExit(main())
