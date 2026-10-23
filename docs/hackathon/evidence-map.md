# Evidence Map

Every claim made in the README and submission is mapped to source code and a
verification command that runs offline.

## Observability

| Claim | Source | Verification |
| --- | --- | --- |
| Async ingest returns 202 Accepted | [ledger_api/main.py](../../../ledger_api/main.py) | `python -m unittest tests.test_api.TestApiContracts.test_ingest_returns_202_and_eventually_stores_cost_and_risk -v` |
| SDK fires and forgets; ignores delivery failures | [ledger/sdk.py](../../../ledger/sdk.py) | `python -m unittest tests.test_api.TestApiContracts.test_frozen_single_span_sdk_contract_is_accepted -v` |
| Project isolation via API keys | [ledger_api/services.py](../../../ledger_api/services.py) | `python -m unittest tests.test_api.TestApiContracts.test_project_isolation -v` |
| Free tier rejects extended retention | [ledger_api/main.py](../../../ledger_api/main.py) | `python -m unittest tests.test_api.TestApiContracts.test_free_tier_rejects_extended_retention -v` |

## Evaluation

| Claim | Source | Verification |
| --- | --- | --- |
| Versioned golden-set evaluation | [ledger/pipeline/golden_set.py](../../ledger/pipeline/golden_set.py) | Offline init: `python -m ledger.pipeline.golden_set init` (creates dataset) |
| Cost attribution from provider tokens | [ledger/pipeline/costs.py](../../ledger/pipeline/costs.py) | `python -m ledger.pipeline.costs test` |
| Regression gate blocks below threshold | [ledger/pipeline/regression.py](../../ledger/pipeline/regression.py) | `python -m ledger.pipeline.regression test` |
| Injection monitoring flags suspicious text | [ledger/pipeline/injection_scan.py](../../ledger/pipeline/injection_scan.py) | `python -m ledger.pipeline.injection_scan test` |
| Release-readiness policy check | [ledger/pipeline/release_policy.py](../../ledger/pipeline/release_policy.py) | `python -m ledger.pipeline.release_policy test` |

## Evidence chain

| Claim | Source | Verification |
| --- | --- | --- |
| Commit provenance binds evidence to Git | [ledger/pipeline/provenance.py](../../ledger/pipeline/provenance.py) | `python -m ledger.pipeline.provenance test` |
| Runtime fingerprint prevents config drift | [ledger/pipeline/runtime_binding.py](../../ledger/pipeline/runtime_binding.py) | `python -m ledger.pipeline.runtime_binding test` |
| Container binding pins evaluation runtime | [ledger/pipeline/container_binding.py](../../ledger/pipeline/container_binding.py) | `python -m ledger.pipeline.container_binding test` |
| Evaluation orchestration runs end-to-end | [ledger/pipeline/orchestration.py](../../ledger/pipeline/orchestration.py) | `python -m ledger.pipeline.orchestration test` |
| Preflight catches issues before spend | [ledger/pipeline/preflight.py](../../ledger/pipeline/preflight.py) | `python -m ledger.pipeline.preflight test` |

## Spend control

| Claim | Source | Verification |
| --- | --- | --- |
| Spend plans require explicit approval | [ledger/pipeline/spend_plan.py](../../ledger/pipeline/spend_plan.py) | `python -m ledger.pipeline.spend_plan test` |
| Cost reconciliation matches plan to usage | [ledger/pipeline/cost_reconciliation.py](../../ledger/pipeline/cost_reconciliation.py) | `python -m ledger.pipeline.cost_reconciliation test` |
| Reservations enforce single-use execution | [ledger/pipeline/spend_reservations.py](../../ledger/pipeline/spend_reservations.py) | `python -m ledger.pipeline.spend_reservations test` |
| Interrupted reservations are recoverable | [ledger/pipeline/reservation_recovery.py](../../ledger/pipeline/reservation_recovery.py) | `python -m ledger.pipeline.reservation_recovery test` |
| Execution context is validated | [ledger/pipeline/execution_context.py](../../ledger/pipeline/execution_context.py) | `python -m ledger.pipeline.execution_context test` |
| Reservation-scoped reconciliation works | [ledger/pipeline/reservation_reconciliation.py](../../ledger/pipeline/reservation_reconciliation.py) | `python -m ledger.pipeline.reservation_reconciliation test` |
| Portable evidence bundles export/restore | [ledger/pipeline/evidence_bundle.py](../../ledger/pipeline/evidence_bundle.py) | `python -m ledger.pipeline.evidence_bundle test` |

## Judge

| Claim | Source | Verification |
| --- | --- | --- |
| Judge parses structured JSON payloads | [judge.py](../../../judge.py) | `python -m unittest tests.test_judge.TestParseJudgePayload -v` |
| Judge coerces score types correctly | [judge.py](../../../judge.py) | `python -m unittest tests.test_judge.TestParseJudgePayload.test_score_is_coerced_to_float -v` |
| Discrimination check validates judge quality | [judge.py](../../../judge.py) | `python -m unittest tests.test_judge.TestHarness -v` |
| Key diagnostics detect provider mismatch | [judge.py](../../../judge.py) | `python -m unittest tests.test_judge.TestKeyDiagnostics -v` |
| Dotenv loader is safe and correct | [judge.py](../../../judge.py) | `python -m unittest tests.test_judge.TestLoadDotenv -v` |

## Infrastructure

| Claim | Source | Verification |
| --- | --- | --- |
| Stable CLI delegates to existing implementations | [ledger/cli.py](../../../ledger/cli.py) | `python -m unittest tests.test_cli -v` |
| Doctor is read-only and never exposes secrets | [ledger/cli.py](../../../ledger/cli.py) | `python -m unittest tests.test_cli.LedgerCliTests.test_malformed_dotenv_secret_is_not_exposed_by_help_or_doctor -v` |
| Legacy modules and commands remain compatible | [tests/test_compatibility.py](../../../tests/test_compatibility.py) | `python -m unittest tests.test_compatibility -v` |
| Descriptive facades delegate without duplication | [ledger/evaluation/](../../../ledger/evaluation/) | `python -m unittest tests.test_compatibility.CompatibilityTests.test_descriptive_facades_import -v` |
| Reviewed PostgreSQL schema | [migrations/001_ledger_schema.sql](../../../migrations/001_ledger_schema.sql) | Manual review |
| GitHub Actions CI runs all offline tests | [.github/workflows/ledger-checks.yml](../../../.github/workflows/ledger-checks.yml) | Push to `main` or open a PR |
| Rumpty Cloud deployment path | [docs/deployment.md](../../../docs/deployment.md), [Dockerfile](../../../Dockerfile) | `python -m ledger doctor --check-database`, then follow the deployment guide and `GET /health` |

