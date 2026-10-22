# Day 21: Reservation-Scoped Cost Reconciliation

## Goal

Make cost reconciliation follow the reservation association established by
Days 18–20 instead of accepting a manually selected candidate.

The flow will verify:

```text
stored reservation
  -> saved Day 14 rehearsal report
  -> reservation-bound candidate
  -> Day 17 cost reconciliation
```

## Scope and boundary

This change covers implementation, offline tests, CI wiring, commit, and pull
request validation. It does not run live reconciliation against PostgreSQL.
It makes no model calls, database writes, refunds, budget releases, or release
policy changes.

The optional live command will be available for a later operator-approved run
against an existing finished Day 20 reservation. It will use the configured
database in read-only mode and will not create a new evaluation.

## Architecture

### Reservation-scoped wrapper

Create [`day21.py`](../../../day21.py) as a wrapper around the existing
Day 17 reconciliation command. It will accept only a reservation UUID:

```text
python day21.py reconcile --reservation RESERVATION_UUID
```

The wrapper will:

1. Create a private `results/day21/<reconciliation-id>/` directory.
2. Open a repeatable-read, read-only PostgreSQL transaction.
3. Load the reservation’s budget ID, state, stored plan, plan hash, reserved
   estimate, associated candidate, saved exit code, rehearsal report path, and
   rehearsal report hash.
4. Require `FINISHED` state and a non-null candidate. Missing evidence never
   implies zero cost.
5. Verify the stored plan’s canonical hash.
6. Read the saved Day 14 report under `results/day14`, verify its hash, and
   validate its reservation context, candidate identity, settings, source,
   image, and decision code.
7. Load the associated candidate configuration, validate its Day 20 context,
   and validate its provenance and coverage metadata using the existing
   Day 19 validation boundary.
8. Snapshot the verified association, write the stored plan to the private
   result directory, and invoke Day 17 using that stored plan and candidate.
9. Verify Day 17’s status, candidate ID, plan payload hash, and exit code.
10. Save a linked Day 21 report containing the reservation, budget, candidate,
    plan/report hashes, Day 17 report path/hash, embedded cost report, and
    explicit read-only/no-model/no-release flags.

Day 17 remains the canonical cost-calculation implementation. Day 21 owns
reservation identity and evidence-chain validation.

### Shared validation boundaries

Reuse:

- `day16.canonical_hash` for stored-plan identity.
- `day19.validate_report` for Day 14 report/plan compatibility.
- `day19.validate_candidate` for candidate provenance checks.
- `day20.validate_context` for report and candidate reservation binding.

No historical report or candidate evidence will be modified. If any binding,
hash, state, or provenance check fails, the Day 21 report remains
`INCONCLUSIVE` with `association_verified: false`.

## Report and exit semantics

Day 21 will use:

```python
VERSION = "ledger-reservation-reconciliation-v1"
CHILD_EXIT_CODES = {
    "RECONCILED_RECORDS": 0,
    "PARTIAL": 2,
    "INCONCLUSIVE": 3,
}
```

Association verification and cost status are separate:

| Association verified | Cost status | Meaning |
|---|---|---|
| `true` | `RECONCILED_RECORDS` | Correctly associated evidence has saved cost records |
| `true` | `PARTIAL` | Association passed but usage or attribution is incomplete |
| `true` | `INCONCLUSIVE` | Association passed but cost reconciliation could not complete |
| `false` | `INCONCLUSIVE` | Reservation, report, or candidate verification failed |

The command will never report a successful reconciliation when the reservation
association is unresolved.

## Error handling and safety

- Non-`FINISHED` reservations are rejected.
- Reservations without an associated candidate are rejected.
- Missing or mismatched plan/report hashes are rejected.
- Missing or mismatched Day 20 context is rejected.
- A report candidate or Day 17 child report for another candidate is rejected.
- A Day 17 report with a mismatched plan hash or exit code is rejected.
- Database access is read-only using a repeatable-read transaction.
- Day 21 itself performs no database writes and does not release capacity.
- Private Day 21 artifacts may contain historical plan metadata and logs; they
  must remain uncommitted and locally protected.

## Testing

Add eight offline tests in `day21.py`:

1. A finished reservation with a candidate is accepted.
2. A running reservation is rejected.
3. A finished reservation without a candidate is rejected.
4. A matching Day 17 child report is accepted.
5. A child report for the wrong candidate is rejected.
6. A child report with the wrong plan hash is rejected.
7. A child report with an inconsistent exit code is rejected.
8. An inconclusive child report may omit its plan hash.

These tests use pure validation helpers and do not require PostgreSQL, Docker,
or model credentials.

Update CI to compile `day21.py` and run `python day21.py test`. Run the focused
Day 21 tests, the complete offline suite, Python compilation, and
`git diff --check`.

## Validation and delivery

The implementation phase will:

- create `day21.py`;
- update [`.github/workflows/ledger-checks.yml`](../../../.github/workflows/ledger-checks.yml);
- run all offline validation;
- commit with the required co-author trailer;
- push and open a pull request;
- verify hosted CI;
- stop before live reconciliation.

A separate explicit approval is required to run
`python day21.py reconcile --reservation ...` against a real reservation.

