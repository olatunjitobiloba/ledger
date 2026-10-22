# Day 20: Reservation-Bound Evidence

## Goal

Bind each reserved evaluation to one explicit execution context and preserve that
context through the generation artifact, candidate configuration, and Day 14
rehearsal report.

The binding improves traceability and prevents finalization or recovery from
accepting evidence produced for a different reservation. It is a consistency
check, not cryptographic authentication: an operator with control of the
environment or database can still forge identifiers.

## Scope and boundary

This change covers implementation, offline tests, CI wiring, commit, and pull
request validation. It does not create or run a fresh paid rehearsal. Direct
Day 14 execution remains supported without a reservation, but unbound evidence
cannot finalize or recover a reservation.

No database migration or dependency-image rebuild is required. The existing
reservation tables and stored plans remain the source of financial state.

## Architecture

### Shared execution context

[`day20.py`](../../../day20.py) will be independent of the earlier day modules
to avoid circular imports. It will define:

- `VERSION = "ledger-execution-context-v1"`
- `LEDGER_SPEND_RESERVATION_ID`
- `LEDGER_SPEND_PLAN_SHA256`
- `make_context(reservation_id, plan_sha256)`
- `context_from_environment(environment=None)`
- `validate_context(stored, reservation_id, plan_sha256)`
- `require_candidate_context(connection, candidate_id, reservation_id, plan_sha256)`

The context contains the normalized reservation UUID, the canonical stored-plan
SHA-256, and the context version. Both environment variables must be present
together and valid. If both are absent, the execution is explicitly unbound.
Partial or malformed values are rejected.

### Evidence propagation

- [`day18.py`](../../../day18.py) will read the stored reservation and plan
  digest, then provide the context only in the child process environment.
  Ordinary unreserved runs will not receive manually exported context.
- [`day13.py`](../../../day13.py) will read the context before application
  calls and save it in the completed generation manifest.
- [`day7.py`](../../../day7.py) will copy the manifest context into the saved
  `ledger_eval_runs.config`.
- [`day14.py`](../../../day14.py) will add the context to the rehearsal report
  immediately after entering its main execution block, including reports for
  failures before candidate creation.

### Finalization and recovery

Day 18 finalization will require:

1. The report context matches the reservation UUID and stored plan hash.
2. The report passes existing baseline, source, image, decision, and exit-code
   checks.
3. If a candidate exists, its saved configuration contains the same context.

Any missing or mismatched context will leave the reservation `UNKNOWN`; it will
not release capacity or accept the evidence.

Day 19 recovery will apply the same report-context check and candidate-context
check before inserting the recovery audit event and marking the reservation
`FINISHED`. Historical reports without context remain unresolved; no context
will be manufactured for old evidence.

## Error handling

- Invalid or incomplete child context fails before model/application calls.
- Missing or mismatched report context rejects finalization or recovery.
- Missing or mismatched candidate context rejects finalization or recovery.
- Existing Day 18/19 conservative behavior remains: failed association leaves
  the reservation consumed and unresolved.
- No model calls, retries, refunds, or budget releases are added.

## Testing

Add eight focused tests in `day20.py` covering:

1. Unbound execution.
2. Complete environment.
3. Partial environment.
4. Empty environment value.
5. Invalid plan hash.
6. Matching context.
7. Wrong reservation.
8. Missing candidate binding.

Run the existing six Day 18 tests, seven Day 19 tests, and eight Day 20 tests,
then run the complete offline suite. Update CI syntax checks and add a dedicated
Day 20 test step.

## Validation and delivery

Before any paid execution:

- compile all changed Python modules;
- run focused and full offline tests;
- run `git diff --check`;
- commit with the required co-author trailer;
- push the branch and open a pull request;
- verify CI passes.

The implementation will stop at that point. A fresh spend plan, reservation,
and paid rehearsal require separate explicit approval.

