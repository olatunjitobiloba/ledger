# Evidence Map

Every claim made in the README and submission is mapped to source code and a
verification command that runs offline.

## Observability

| Claim | Source | Verification |
| --- | --- | --- |
| Async ingest returns 202 Accepted | [ledger_api/main.py](../../../ledger_api/main.py) | `python -m unittest test_api.TestApiContracts.test_ingest_returns_202_and_eventually_stores_cost_and_risk -v` |
| SDK fires and forgets; ignores delivery failures | [ledger_sdk.py](../../../ledger_sdk.py) | `python -m unittest test_api.TestApiContracts.test_frozen_single_span_sdk_contract_is_accepted -v` |
| Project isolation via API keys | [ledger_api/services.py](../../../ledger_api/services.py) | `python -m unittest test_api.TestApiContracts.test_project_isolation -v` |
| Free tier rejects extended retention | [ledger_api/main.py](../../../ledger_api/main.py) | `python -m unittest test_api.TestApiContracts.test_free_tier_rejects_extended_retention -v` |

## Evaluation

| Claim | Source | Verification |
| --- | --- | --- |
| Versioned golden-set evaluation | [day3.py](../../../day3.py) | Offline init: `python day3.py init` (creates dataset) |
| Cost attribution from provider tokens | [day5.py](../../../day5.py) | `python day5.py test` |
| Regression gate blocks below threshold | [day6.py](../../../day6.py) | `python day6.py test` |
| Injection monitoring flags suspicious text | [day8.py](../../../day8.py) | `python day8.py test` |
| Release-readiness policy check | [day9.py](../../../day9.py) | `python day9.py test` |

## Evidence chain

| Claim | Source | Verification |
| --- | --- | --- |
| Commit provenance binds evidence to Git | [day11.py](../../../day11.py) | `python day11.py test` |
| Runtime fingerprint prevents config drift | [day12.py](../../../day12.py) | `python day12.py test` |
| Container binding pins evaluation runtime | [day13.py](../../../day13.py) | `python day13.py test` |
| Evaluation orchestration runs end-to-end | [day14.py](../../../day14.py) | `python day14.py test` |
| Preflight catches issues before spend | [day15.py](../../../day15.py) | `python day15.py test` |

## Spend control

| Claim | Source | Verification |
| --- | --- | --- |
| Spend plans require explicit approval | [day16.py](../../../day16.py) | `python day16.py test` |
| Cost reconciliation matches plan to usage | [day17.py](../../../day17.py) | `python day17.py test` |
| Reservations enforce single-use execution | [day18.py](../../../day18.py) | `python day18.py test` |
| Interrupted reservations are recoverable | [day19.py](../../../day19.py) | `python day19.py test` |
| Execution context is validated | [day20.py](../../../day20.py) | `python day20.py test` |
| Reservation-scoped reconciliation works | [day21.py](../../../day21.py) | `python day21.py test` |
| Portable evidence bundles export/restore | [day22.py](../../../day22.py) | `python day22.py test` |

## Judge

| Claim | Source | Verification |
| --- | --- | --- |
| Judge parses structured JSON payloads | [judge.py](../../../judge.py) | `python -m unittest test_judge.TestParseJudgePayload -v` |
| Judge coerces score types correctly | [judge.py](../../../judge.py) | `python -m unittest test_judge.TestParseJudgePayload.test_score_is_coerced_to_float -v` |
| Discrimination check validates judge quality | [judge.py](../../../judge.py) | `python -m unittest test_judge.TestHarness -v` |
| Key diagnostics detect provider mismatch | [judge.py](../../../judge.py) | `python -m unittest test_judge.TestKeyDiagnostics -v` |
| Dotenv loader is safe and correct | [judge.py](../../../judge.py) | `python -m unittest test_judge.TestLoadDotenv -v` |

## Infrastructure

| Claim | Source | Verification |
| --- | --- | --- |
| Stable CLI delegates to existing implementations | [ledger/cli.py](../../../ledger/cli.py) | `python -m unittest tests.test_cli -v` |
| Doctor is read-only and never exposes secrets | [ledger/cli.py](../../../ledger/cli.py) | `python -m unittest tests.test_cli.LedgerCliTests.test_malformed_dotenv_secret_is_not_exposed_by_help_or_doctor -v` |
| Legacy modules and commands remain compatible | [tests/test_compatibility.py](../../../tests/test_compatibility.py) | `python -m unittest tests.test_compatibility -v` |
| Descriptive facades delegate without duplication | [ledger/evaluation/](../../../ledger/evaluation/) | `python -m unittest tests.test_compatibility.CompatibilityTests.test_descriptive_facades_import -v` |
| Reviewed PostgreSQL schema | [migrations/001_ledger_schema.sql](../../../migrations/001_ledger_schema.sql) | Manual review |
| GitHub Actions CI runs all offline tests | [.github/workflows/ledger-checks.yml](../../../.github/workflows/ledger-checks.yml) | Push to `main` or open a PR |
| Rumpty Cloud deployment | [docs/deployment.md](../../../docs/deployment.md), [Dockerfile](../../../Dockerfile) | `GET /health` on deployed instance |
