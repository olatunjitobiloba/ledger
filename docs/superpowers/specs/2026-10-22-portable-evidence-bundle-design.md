# Day 22: Portable Reservation Evidence

## Goal

Package a finished reservation’s verified plan and original Day 14 rehearsal
report into a small portable archive that can be restored on another machine
without losing the historical report association.

The archive is anchored by comparison with the trusted reservation and
candidate records in PostgreSQL. It is not signed and is not a full database,
execution-log, provider-invoice, or evaluation-output backup.

## Scope and boundary

This change covers implementation, eight offline tests, CI wiring, commit, and
pull request validation. It does not perform live export or restore, access a
real database, create a real evidence archive, or configure external
retention. It makes no model calls, database writes, retries, refunds, or
release-policy changes.

A later operator-approved exercise may export a finished Day 20 reservation,
copy the archive to an access-controlled durable store, restore it on another
machine, and run Day 21 reconciliation.

## Architecture

### Standalone bundle utility

Create [`day22.py`](../../../day22.py) with three commands:

```text
python day22.py test
python day22.py export --reservation RESERVATION_UUID --output PATH.zip
python day22.py restore --bundle PATH.zip
```

The utility will reuse:

- `day16.canonical_hash` for stored-plan identity;
- `day19.validate_candidate` for candidate provenance and coverage metadata;
- `day20.validate_context` for reservation binding;
- `day21.require_finished_candidate` and `day21.validate_association` for
  finished-reservation and report/plan compatibility checks.

### Archive format

Each archive contains exactly these three members:

```text
manifest.json
plan.json
rehearsal.json
```

`plan.json` contains the reserved plan serialized canonically for transport.
`rehearsal.json` contains the original Day 14 report bytes without
re-serialization. `manifest.json` contains the bundle version, reservation and
candidate IDs, reservation plan/report path, plan hash, and SHA-256 hashes for
the two evidence files.

The archive is bounded to 32 MiB total and 8 MiB per member. Directories,
encrypted members, missing members, unexpected members, duplicate names, and
oversized expanded members are rejected. Archive-supplied paths are never
extracted directly.

### Export flow

1. Read the reservation in a repeatable-read, read-only transaction.
2. Require `FINISHED` state and a non-null candidate.
3. Verify the stored plan hash, candidate context/provenance, and report path.
4. Read the original report from the local `results/day14` path and verify its
   exact ledger hash.
5. Re-read the ledger association against that report and reject changes
   between the two snapshots.
6. Serialize the stored plan canonically, create the three-member archive, and
   publish it using atomic no-overwrite semantics.

An existing identical archive may be reused. A different existing output is
rejected.

### Restore flow

1. Read and size-check the archive without extracting paths.
2. Verify exact members and manifest/file hashes.
3. Load the reservation UUID, plan, and report from the archive.
4. Re-verify the bundled plan, report context, candidate identity, report path,
   candidate context, and candidate provenance against the receiving database
   in a repeatable-read, read-only transaction.
5. Verify the exact bundled report bytes against the ledger’s original report
   hash.
6. Publish only to the original relative
   `results/day14/<REHEARSAL_UUID>/report.json` destination.

An identical destination is reported as `ALREADY_PRESENT`; different content
is rejected and never replaced. Publication uses a temporary file and a hard
link, failing rather than falling back to overwrite-prone behavior.

## Error handling and safety

- Only `FINISHED` candidate-associated reservations can be exported.
- Missing, malformed, mismatched, or changed evidence is rejected.
- Path traversal, absolute paths, Windows separators, non-canonical UUID
  directory names, symlinking archive paths, and archive member surprises are
  rejected.
- Database operations are read-only; no reservation or budget row changes.
- Archives are not signed and do not establish trust without the same ledger
  database.
- Generated bundles and restored historical evidence remain private and are
  not committed to the repository.

## Testing

Add eight offline tests in `day22.py`:

1. Accept a canonical report path.
2. Reject traversal.
3. Reject an absolute path.
4. Reject an evidence hash mismatch.
5. Accept matching manifest hashes.
6. Reuse an identical existing output.
7. Reject different existing output without changing it.
8. Reject an unexpected archive member.

These tests use temporary files and in-memory archive construction only. They
do not require PostgreSQL, Docker, model credentials, real reservations, or
external storage.

Update CI to compile `day22.py` and run `python day22.py test`. Run focused
Day 22 tests, the complete offline suite, Python compilation, and
`git diff --check`.

## Validation and delivery

The implementation phase will:

- create `day22.py`;
- update [`.github/workflows/ledger-checks.yml`](../../../.github/workflows/ledger-checks.yml);
- run all offline validation;
- commit with the required co-author trailer;
- push and open a pull request;
- verify hosted CI;
- stop before any live export, restore, archive retention, or Day 21 run.

A separate explicit approval is required for a real evidence portability
exercise using a finished reservation and access-controlled durable storage.

