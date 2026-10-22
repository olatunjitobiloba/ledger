"""Day 22: portable reservation evidence bundle primitives.

    python day22.py test
    python day22.py export --reservation RESERVATION_UUID --output PATH.zip
    python day22.py restore --bundle PATH.zip
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

from day4 import connect
from day16 import canonical_hash
from day19 import validate_candidate
from day20 import validate_context
from day21 import require_finished_candidate, validate_association


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
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_plan_bytes(plan: dict[str, Any]) -> bytes:
    if not isinstance(plan, dict):
        raise ValueError("Plan must be an object.")
    return _canonical_json(plan)


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
    if verify_member_hash(plan_bytes, manifest.get("plan_sha256")) != sha256(plan_bytes):
        raise ValueError("Plan hash does not match manifest.")
    if verify_member_hash(rehearsal_bytes, manifest.get("rehearsal_sha256")) != sha256(rehearsal_bytes):
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
            if info.file_size > MAX_MEMBER_BYTES:
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
            if path.is_file() and not path.is_symlink() and path.read_bytes() == content:
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
    with connect() as connection:
        with connection.transaction():
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
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
                config.get("execution_context")
                if isinstance(config, dict)
                else None,
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


class PortableEvidenceBundleTests(unittest.TestCase):
    def manifest(self, plan: bytes, rehearsal: bytes) -> dict[str, Any]:
        return {
            "version": VERSION,
            "signed": False,
            "plan_sha256": sha256(plan),
            "rehearsal_sha256": sha256(rehearsal),
        }

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
                    os.symlink(target, workspace / "results" / "day14", target_is_directory=True)
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
                        {"version": "wrong", "signed": False,
                         "plan_sha256": sha256(plan),
                         "rehearsal_sha256": sha256(rehearsal)}
                    ).encode()
                    if name == "manifest.json"
                    else {"plan.json": plan, "rehearsal.json": rehearsal}[name]
                )
                rewritten.writestr(name, raw)
        self.assertNotEqual(archive, output.getvalue())
        with self.assertRaises(ValueError):
            read_archive_from_bytes(output.getvalue())


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("test")
    export = subparsers.add_parser("export")
    export.add_argument("--reservation", required=True, type=uuid.UUID)
    export.add_argument("--output", required=True, type=Path)
    restore = subparsers.add_parser("restore")
    restore.add_argument("--bundle", required=True)
    args = parser.parse_args()
    if args.command == "test":
        result = unittest.main(argv=[sys.argv[0], "PortableEvidenceBundleTests"], exit=False)
        return 0 if result.result.wasSuccessful() else 1
    if args.command == "export":
        return export_reservation(args)
    raise SystemExit("Restore is reserved for a later task.")


if __name__ == "__main__":
    raise SystemExit(main())
