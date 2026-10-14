# Provider and processing truthfulness

Baseline: `494c409a0785208cf3600ddb1e0fa26d9d00efbd` (tracked checkout clean; existing untracked `output/`).

The old factory returned `mode=mongodb` with MockLLM and MockWorkflow. Services interpreted any non-mock mode as live reasoning, translation or drafting. Unknown database configuration could fall through to DynamoDB/S3; storage configuration could silently select mock. The workflow selection always used mock even on the old real branch.

Provider selection is now independent. Absent configuration intentionally defaults to MongoDB, GridFS, MockLLM and MockWorkflow. `USE_MOCK_AWS=true` is the legacy local JSON/files default; false does not enable AWS. Explicit provider variables take precedence over legacy per-dimension flags. `USE_REAL_DATABASE=true`, `USE_REAL_STORAGE=true`, `USE_REAL_LLM=true` remain explicit legacy opt-ins only when their respective provider variable is absent. Boolean flags accept only true/false. Dotenv loads once without overriding process configuration; the factory reads the current environment at each invocation.

| Variable | Accepted values (canonical result) |
| --- | --- |
| DATABASE_PROVIDER | mongodb/mongo/community (mongodb), mock, dynamodb/real (dynamodb) |
| OBJECT_STORE_PROVIDER | mongodb/gridfs/local (mongodb), mock, s3/aws/real (s3) |
| LLM_PROVIDER | mock, bedrock/real (bedrock) |
| WORKFLOW_PROVIDER | mock, real (unimplemented; unavailable) |
| EMAIL_PROVIDER | disabled (default), mock (development only), ses (explicit AWS opt-in) |

All selectors are validated before construction. Blank, malformed or unsupported explicit values raise a configuration error without echoing arbitrary values. The independent object-store API also rejects an explicitly empty argument. AWS database/storage imports are lazy and occur only when selected. Local startup does not import or require the AWS SDK. Auth continues using the existing database-backed local identity implementation. Legal retrieval remains the existing local corpus reader (or fixture reader under the explicit legacy mock flag); neither implies live reasoning.

AdapterSet exposes persistence_provider, object_store_provider, llm_provider, workflow_provider and separate LLM/workflow capability states. Mock adapters declare mock. The real workflow is still a NotImplemented stub and declares unavailable. Bedrock readiness requires nonblank model/region and a bearer token or explicit access-key/secret pair. This is local configuration validation, NOT a remote credential, model-access or service-availability probe. Profile/instance-role credential chains are not advertised as ready by this conservative check. No live external execution was validated by this task.

Processing derivation: both mock -> mock; both live -> live; live/mock -> hybrid; either unavailable or unrecognized capability -> unavailable. Database/storage never participate. No shipped workflow is currently live, so this build cannot truthfully report fully live processing. Deterministic live workflow doubles exercise the future live combination without activating it in production. Production startup rejects mock/hybrid/unavailable processing.

`adapters.mode` is a read-only derived compatibility alias for processing_mode. It never returns mongodb or real. `/api/health` retains adapter_mode with these semantics and adds providers, processing_mode, component capabilities and email_provider, without credentials. Its status=ok indicates application startup, not remote provider availability. Frontend diagnostics now label processing and show database/storage separately. Remove the compatibility field/property after external clients migrate to the explicit fields.

Every former combined-mode service consumer was audited: core_workflow, understanding_agents, legal_registry, legal_team, legal_analysis, input_declarations, input_layer, engine1, engine2, engine3, analysis status, health and guest_claims. Reasoning/translation/drafting check LLM capability; fixture injection checks specifically mock; stored and returned processing labels use processing_mode. Engine 2 received only a diagnostic-label replacement and was not started. Existing phase3/phase4 synthetic test-double hooks are retained. Legal policies and decisions were not changed. SES no longer follows a persistence/processing comparison: disabled fails closed, mock is explicit development-only, SES is explicit. The mock launcher sets explicit dimensions so inherited configuration cannot override its intent.

Validation uses synthetic data and UUID temporary Mongo databases, including a fresh-process application lifespan/health/CRUD/GridFS test with AWS imports forbidden and credentials blank. No S3 probe, live AWS call, production migration, real review write, or ingestion-prework connection was performed. Existing synthetic migration regression tests exercise fixtures only. The existing untracked output directory is not committed.

Protected SHA-256 before and after (must remain identical):
- Authority database: `B96220116AC40A01B4F96E6B620EDC7EEBFA35D39D11DFB33B677B9BF67716C3`
- Identity database: `BD055FE4BD996ABA38A243FBB3572F68646BE7CD469E0382A3B57920A9A15B17`

Can MongoDB persistence still be mistaken for live LLM/workflow processing? No in the corrected runtime guards and diagnostics; external clients must adopt the documented compatibility semantics.

Can an unknown provider value silently fall through to AWS or mock behavior? No.

Does the health endpoint independently report persistence, storage and processing? Yes.

Can CaseSeva still run locally with MongoDB/GridFS and zero AWS dependency? Yes, verified with AWS SDK imports blocked in a fresh process.

Was any real legal authority or review state changed? No.

No provider configuration was allowed to silently change legal-processing truthfulness.

No legal authority was approved or modified by this task.

Engine 2 was NOT started.

Phase 5 was NOT started.

Changed files (including explicit-capability updates to synthetic test adapters):

- `.env.example`
- `README.md`
- `backend/adapters/capabilities.py`
- `backend/adapters/factory.py`
- `backend/adapters/mock/llm.py`
- `backend/adapters/mock/workflow.py`
- `backend/adapters/real/llm.py`
- `backend/adapters/real/workflow.py`
- `backend/routes/analysis.py`
- `backend/routes/guest_claims.py`
- `backend/routes/health.py`
- `backend/services/core_workflow.py`
- `backend/services/engine1.py`
- `backend/services/engine2.py`
- `backend/services/engine3.py`
- `backend/services/input_declarations.py`
- `backend/services/input_layer.py`
- `backend/services/legal_analysis.py`
- `backend/services/legal_registry.py`
- `backend/services/legal_team.py`
- `backend/services/understanding_agents.py`
- `backend/storage/object_store.py`
- `backend/tests/core_test_support.py`
- `backend/tests/helpers.py`
- `backend/tests/test_case_driven_multi_domain.py`
- `backend/tests/test_common_input.py`
- `backend/tests/test_core_contracts.py`
- `backend/tests/test_current_genericity_audit.py`
- `backend/tests/test_engine3.py`
- `backend/tests/test_entry_routes.py`
- `backend/tests/test_genericity_audit.py`
- `backend/tests/test_input_layer.py`
- `backend/tests/test_legal_foundation.py`
- `backend/tests/test_legal_team.py`
- `backend/tests/test_mongo_persistence.py`
- `backend/tests/test_production_mode.py`
- `backend/tests/test_provider_truthfulness.py`
- `backend/tests/test_understanding_agents.py`
- `backend/tests/test_understanding_sources.py`
- `docs/provider-processing-truthfulness.md`
- `frontend/src/components/AppHeader.jsx`
- `frontend/src/pages/HomePage.jsx`
- `scripts/backend.cjs`
- `scripts/smoke_test_live.py`
- `scripts/verify_aws_disabled_runtime.py`
- `scripts/verify_mongo_migration.py`

Validation results:
- Broad backend run: 307 tests; 304 passed initially, with three failures investigated. AWS client/resource constructors were blocked for the run. No Engine 2 test module was run.
- Blackboard + orchestration + current genericity rerun: 38 passed. Both multiprocessing failures were caused by launching the original Windows runner from stdin and disappear with `python -m unittest`.
- The remaining understanding-agent test also failed on an untouched archive of baseline 494c409. Its old FAKE_DOMAIN rejection contradicted the completed open-domain genericity behavior. Only its fixture was changed to an actually malformed domain identifier; no legal/domain decisions changed.
- Corrected understanding-agent regression: 1 passed in 19.050 seconds. All initial broad-run failures are resolved by the targeted reruns above; this is not a claim that a second full broad run was performed.
- Final provider matrix: 10 passed, including fresh-process real Mongo/GridFS startup with boto3/botocore imports forbidden, health matrix, invalid/blank selectors, explicit AWS selection using doubles, independent persistence/storage combinations, and unavailable workflow/LLM cases.
- Provider, production, guard, common-input and drafting run: 40 tests; 39 passed and one stale message assertion needed updating after unavailable-LLM wording was corrected. That drafting test and the new disabled-email regression then passed (2 tests).
- Frontend production build passed. Python compileall for backend, scripts and engineering_prework and git diff --check passed.
- The system Python lacked pymongo; validation used the existing project `.venv/Scripts/python.exe`. No dependencies were installed or changed.

The final local commit is reported in the chat; this report is included in that commit. No push is performed.

Final post-test SHA-256 comparison passed for both protected JSON files; the before/after values above are identical.
