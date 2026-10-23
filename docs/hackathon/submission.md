# Hackathon Submission: Ledger

## One-line pitch

Ledger is production AI reliability infrastructure that ensures every model
change ships with evidence it did not regress — built for Rumpty Cloud in
22 days.

## The problem

AI teams ship model updates without a repeatable way to prove quality held.
Manual spot-checks miss regressions. Cost is invisible until the invoice.
Prompt injection is hard to detect. There is no portable proof that a release
was safe.

## The solution

Ledger provides four connected systems:

1. **Asynchronous observability** — a fire-and-forget SDK and API that records
   trace cost and injection-risk metadata without blocking the host
   application's AI response.

2. **Automated evaluation gates** — versioned golden-set scoring with a
   regression threshold that blocks releases below the safety floor.

3. **Spend control** — estimated cost attribution, spend plans, single-use
   reservations, and reconciliation to prevent budget overruns during
   evaluation.

4. **Portable release evidence** — commit-bound, runtime-bound,
   container-bound evaluation bundles that can be exported, restored, and
   verified on any machine.

## What makes this different

- **Evidence chain, not just metrics.** Every release links evaluation results
  to the exact commit, runtime configuration, and container digest that
  produced them. This chain is exportable and independently verifiable.

- **Non-blocking by design.** The SDK deliberately ignores delivery failures.
  Observability never slows or breaks the host application.

- **Offline-verifiable.** 55 tests run without a database, provider key, or
  network access. Every claim in this submission can be verified by cloning the
  repository and running `python -m unittest discover -v`.

- **Production deployment path.** The API and worker ship from one Docker image
  with a managed PostgreSQL database, SSL certificate verification, and a
  reviewed migration-based schema. `docs/deployment.md` is the end-to-end path.

## Architecture

```text
Application
  └─ Ledger SDK (fire-and-forget)
       └─ POST /v1/ingest  ──▸  PostgreSQL job queue
                                     │
                  API ◂── Postgres metadata + blob storage
                                     │
                           Worker ──▸ Judge ──▸ Alerts
                                     │
                           Evaluation pipeline (offline)
                             ├─ Golden-set scoring
                             ├─ Regression gate
                             ├─ Spend planning & reconciliation
                             └─ Portable evidence bundles
```

## Proof points

| Claim | Verification |
| --- | --- |
| Async ingest returns 202, never blocks | `python -m unittest test_api -v` |
| SDK redaction and privacy controls work | `python -m unittest test_api -v` (free-tier test) |
| Judge parses, coerces, and discriminates | `python -m unittest test_judge -v` (33 tests) |
| Strict-rubric Groq judge parses schema-constrained JSON | `python -m unittest test_judge_groq -v` (6 tests) |
| Cost attribution from provider tokens | `python -m ledger.pipeline.costs test` |
| Regression gate blocks below threshold | `python -m ledger.pipeline.regression test` |
| Injection monitoring flags suspicious text | `python -m ledger.pipeline.injection_scan test` |
| Release policy aggregates multiple checks | `python -m ledger.pipeline.release_policy test` |
| Commit provenance binds evidence to Git | `python -m ledger.pipeline.provenance test` |
| Runtime fingerprint prevents config drift | `python -m ledger.pipeline.runtime_binding test` |
| Container binding pins evaluation runtime | `python -m ledger.pipeline.container_binding test` |
| Evaluation orchestration runs end-to-end | `python -m ledger.pipeline.orchestration test` |
| Preflight catches issues before spend | `python -m ledger.pipeline.preflight test` |
| Spend plans require explicit approval | `python -m ledger.pipeline.spend_plan test` |
| Cost reconciliation matches plan to usage | `python -m ledger.pipeline.cost_reconciliation test` |
| Reservations enforce single-use execution | `python -m ledger.pipeline.spend_reservations test` |
| Interrupted reservations are recoverable | `python -m ledger.pipeline.reservation_recovery test` |
| Execution context is validated | `python -m ledger.pipeline.execution_context test` |
| Reservation-scoped reconciliation works | `python -m ledger.pipeline.reservation_reconciliation test` |
| Portable evidence bundles export/restore | `python -m ledger.pipeline.evidence_bundle test` |
| Stable CLI and doctor run offline | `python -m unittest tests.test_cli -v` |
| Legacy compatibility preserved | `python -m unittest tests.test_compatibility -v` |
| Rumpty deployment path with managed PostgreSQL | Follow `docs/deployment.md`, then `GET /health` |

## Honest limitations

- Not a full observability platform — no dashboards, distributed tracing UI,
  or log aggregation.
- Evaluation quality depends on the judge model (Groq-hosted gpt-oss by
  default; model and rubric versions are recorded with each run).
- Injection monitoring is heuristic — a match is suspicion, not proof.
- Cost estimates are approximate when provider-reported actual cost is
  unavailable.
- Single-region Rumpty Cloud deployment; no multi-region failover.
- No user-facing web dashboard; API and CLI access only.

## Demo commands

```bash
# 1. Verify repository readiness (no database, no keys)
python -m ledger doctor

# 2. Run the full offline test suite
python -m unittest test_judge test_judge_groq test_api -v
python -m unittest tests.test_compatibility tests.test_cli -v

# 3. Run evaluation module tests
python -m ledger.pipeline.evidence_bundle test   # portable evidence
python -m ledger.pipeline.regression test    # regression gate
python -m ledger.pipeline.injection_scan test    # injection monitoring

# 4. Show the stable CLI
python -m ledger --help
python -m ledger evidence export --help
```

## Team

Built by Olatunji Oluwatobiloba Franklin as a solo project for the DevCenter
Hacktoberfest hackathon.
