# Phase 1 — Common Multimodal Input Layer

Date: 11 October 2026. Accepted baseline: `d3dfea2`.
Backend implementation commit: `5422c7d`. The following frontend/report commit completes this delivery.

## Delivery status

IMPLEMENTED: shared ingestion, source provenance, conservative content deduplication, uploaded/declared/unavailable/unknown states, input-only retry, Tamil-capable local OCR, background media dispatch, and intake UI changes.
UNIT TESTED: 86 backend tests passed, including 16 new input tests and the unchanged 10 security-hotfix regressions. 16 browser tests passed.
LIVE CONNECTED: Bedrock; authenticated STS; existing S3 bucket. Local OCR uses actual English/Tamil Tesseract data.
LIVE INPUT VALIDATED: English/Tamil/mixed typed input through Bedrock; actual TXT/DOCX/digital PDF/image/screenshot/scanned PDF extraction; S3 temporary-object byte round trip.
PERSISTENCE: LOCAL VALIDATED — DYNAMODB LIVE ACCESS BLOCKED BY AWS SCP.
NOT LIVE INPUT VALIDATED: audio/video speech-to-text. Transcribe is denied by Organizations SCP in the configured processing region. Microphone capture/upload was validated with Chromium's synthetic audio device, not a human speaking Tamil.
END-TO-END VALIDATED: local browser workflows only. No complete live cloud multimodal workflow claim.
LEGAL CORPUS READY: not changed or assessed by this phase.

## Architecture changes and boundaries

All three origins continue using `build_raw_package`: CITIZEN_SELF_SERVICE, CITIZEN_DIRECT_ADVOCATE, ADVOCATE_WALK_IN. Existing case IDs, autosave, access grants and consent checks remain intact. No separate ingestion pipeline was introduced.

Typed text and original uploaded bytes are preserved. Each readable source retains its own text and provenance. Canonicalization collapses exact normalized duplicates, sufficiently long contained text and exact token overlap; it does not fuzzy-merge conflicting amounts or dates. Duplicate uploads retain separate E IDs and a `duplicate_of` link. This preserves evidence selection and provenance while avoiding duplicate combined narrative text. English/Tamil Unicode normalization and whitespace normalization do not rewrite names or numeric values.

Availability classification uses a structured Bedrock response selecting explicitly indexed source passages. The server supplies the exact quote. Literal bilingual guards reject unsupported states and preserve explicit statements omitted by the model. No declaration receives an uploaded evidence ID. Development mode uses explicitly labelled limited rules, not a fake live result. Model-declared availability remains an interpretation of the user's statement and may need review; it is not evidence verification.

Language conversion preserves original source content and checks that original numeric tokens survive. Names, legal names and other translated content still need review: the English working representation is not a certified translation. Failed conversion is marked pending rather than substituted with made-up text.

Uploads save recordings without waiting for transcription in an HTTP request. Shared background ingestion performs real Transcribe calls when configured and permitted. Video currently processes its audio track only; `visual_analysis` is NOT_PERFORMED. Input-only retry dispatches the existing ingestion worker, preserves the case journey state, rejects concurrent retries, and refuses to overwrite a newer input version. Changed extracted content marks an existing foundation stale using the existing status helper.

Security hotfix restrictions remain: retired routes still reject requests, projections still exclude professional/private fields and nested raw content, and citizen diagnostics remain safe. The only projection additions are safe input metadata, input progress and a review-needed flag.

Engine 1/2/3 processing modules, Master Orchestrator, domain specialists, legal retrieval, filing integration and the DynamoDB adapter were not modified.

## Raw Case Package contract

`backend/models/input.py` defines the versioned contract. Legacy engine input keys remain available.

| Group | Fields |
|---|---|
| Identity/version | schema_version, case_id, origin, case_type, case_stage, version, input_version, created_at |
| Context | preferred_language, optional_fields |
| Narrative/content | original_story, canonical_narrative, original_text, original_language_content, canonical_hash, canonical_segments |
| Language | english_working_text, language (provider language, script detection, status, fidelity/review metadata) |
| Uploads | evidence, evidence_ids; actual file IDs only, extraction result and duplicate_of per item |
| Availability | declared_evidence, unavailable_evidence, unknown_evidence, unknown_details |
| Source records | provenance: source_id, actor_id, case_id, case_origin, source_type, original_filename, mime_type, uploaded_at, extraction_method/status, language, content_hash, text_hash, storage_reference, derived_reference, processing_mode, error_state, original_text, optional evidence_id |
| Processing | source_statuses, declaration_processing, pending, processing_mode |

`derived_reference` addresses the source's derived OCR/transcript record inside the package. Storage references and internal error reasons stay internal. `pending` records unresolved extraction, narration, language or declaration failures. Mixed PDFs preserve successfully read pages even when another page fails. OCR completion means text was extracted, not that its accuracy is guaranteed.

## Modality validation

| Input | Implemented | Unit/contract coverage | Actual-content validation |
|---|---|---|---|
| English/Tamil/mixed typed text | Yes | Yes | Bedrock language and availability processing passed |
| TXT | Yes | Yes | Tamil and mixed content preserved |
| DOCX | Yes | Yes | Real mixed-language document extracted |
| Digital PDF | Yes | Yes | Existing Tamil PDF extracted; Rs. 24,500 retained |
| Scanned English PDF | Yes | Partial-page/failure tests | Actual OCR retained test text and amount |
| Scanned Tamil PDF | Yes | Shared PDF/OCR path | Existing Tamil image embedded at normal page size, OCR and amount check passed |
| Image/screenshot | Yes | OCR failure tests | English image/screenshot and Tamil image processed using actual OCR |
| Multiple/duplicate files | Yes | Yes | Browser duplicate upload and local package provenance tests passed |
| Microphone | Capture/upload implemented | Browser capture and API tests | Chromium synthetic device; transcription not validated |
| Uploaded audio | Shared transcription path | Provider test double and failure tests | Live speech blocked by Transcribe SCP |
| Uploaded video | Audio extraction/transcription path | Provider test double and failure tests | Live speech blocked; visual analysis not implemented |
| Unsupported legacy formats | Retained, pending conversion | Failure path | Not claimed as parsed |

Document subject matter (FIR, order, agreement, receipt, invoice, bank statement, payslip, chat, email) is supported through these formats. This phase does not perform legal interpretation of those documents.

## Tamil refrigerator acceptance

The final real Bedrock ingestion-only run passed the scripted assertions. No legal engine ran.

- Original Tamil story retained, including Rs. 24,500; purchase 3 September 2026; delivery 5 September; problem and same-day phone complaint 9 September; message 10 September; repair/replacement request 20 September; follow-up 1 October; unresolved as stated on 10 October.
- AVAILABLE_NOT_UPLOADED: purchase receipt, bank transaction record, text-message screenshots.
- NOT_AVAILABLE: warranty card, phone-call recording, written inspection report.
- UNKNOWN: employee's full name, exact visit date, cause of malfunction; the story's unknown purchase conditions also remain unknown.
- Uploaded evidence IDs: `[]`. No mentioned document became E001/E002/E003.
- Tamil image and normal-sized scanned-PDF extraction preserved the amount. OCR is still marked as needing review; an initial oversized-page test produced an amount recognition error. This is not a blanket OCR accuracy guarantee.

The checked-in fictional text fixture is `backend/tests/fixtures/tamil_refrigerator.txt`. Local detailed outputs are in `.localdev/phase1-validation/`. The final nonsecret validation summary is committed as `artifacts/phase1_input_validation.json`.

## AWS and runtime validation

- STS: account 370401801549 authenticated in us-east-1.
- Existing S3 bucket: accessible, physically in ap-southeast-2. A uniquely named fictional UTF-8 object was uploaded with server-side encryption, downloaded byte-for-byte and deleted. No existing case content changed.
- Bedrock: the existing ap-southeast-2 model configuration remained live. Final validation used six real calls for Tamil, English and mixed input. Earlier diagnostic runs also made calls.
- DynamoDB: user-confirmed ListTables, DescribeTable and GetItem are blocked by Organizations SCP. No further DynamoDB probes after that instruction; no persistence redesign or replacement resource.
- Transcribe: us-east-1 returned AccessDeniedException; the application's configured ap-southeast-2 region explicitly reports an SCP denial. No transcription job was started and no speech result was fabricated.
- AWS CLI login worked while the old Python SDK did not recognize it. Updated to boto3[crt] 1.43.111; native SDK STS and S3 then worked. No credentials were copied into repository files.
- Tesseract English/Tamil data installed under ignored `.localdev/tessdata` with SHA-256 checks. `scripts/setup-input-ocr.py` reproduces this. The binary was already installed; FFmpeg was already present.
- No paid infrastructure provisioned; no organization/IAM policies changed. Existing Bedrock inference consumes model tokens; any future allowed Transcribe run would consume audio-duration billing plus temporary S3 requests/storage.

AWS documents login-session support and CRT requirements: https://docs.aws.amazon.com/boto3/latest/guide/credentials.html
Tamil is listed for batch language identification: https://docs.aws.amazon.com/transcribe/latest/dg/lang-id-batch.html
Official OCR data: https://github.com/tesseract-ocr/tessdata_fast

## Test results and discovered failures

- Initial input/security/entry checks: 20 passed.
- New input suite: 15 passed, later expanded to 16 with a known-fact rejection regression.
- Combined final focused input/security suite: 26 passed.
- Full backend suite: 85 passed initially; final 86 passed after the additional regression and SDK update.
- Initial browser run: 15 passed, 1 failed on the story label after reload. Explicit label association fixed it. Focused rerun: 2 passed. Final full browser run: 16 passed.
- Frontend production builds passed, including the final build.
- `pip check`: no broken requirements. `git diff --check`: passed.
- Real input validation: final script passed all eight local-file modality checks and three language/availability checks. Early model quote/index and known-fact classification issues were rejected and corrected. One acceptance assertion was corrected to use the sample's actual Tamil inflection; the underlying unknown detail had been preserved.

## Remaining blockers and limits

1. DynamoDB live access is BLOCKED BY AWS SCP. Use local persistence; do not retry or bypass the organization restriction.
2. Real speech-to-text is BLOCKED by Transcribe SCP. No human Tamil audio or video narration has passed live transcription. MEDIA_S3_BUCKET and ENABLE_AWS_MEDIA are not enabled; do not enable them while access is denied. When permission is approved, reuse an approved existing private bucket in the processing region. Required capabilities include Transcribe start/get/delete jobs and S3 put/get/delete of the temporary prefix; no replacement infrastructure is currently needed.
3. Video visual understanding is not implemented. Only audio processing is supported by this path.
4. Production Lambda packaging of Tesseract language data and FFmpeg remains pending. Local OCR validation does not establish deployed OCR readiness. No deployment was performed.
5. OCR and translation require review for recognition/transliteration mistakes. Literal deduplication intentionally does not merge paraphrases or ambiguous fuzzy matches.
6. Availability extraction is conservative and does not support every possible phrasing. Rejected model classifications remain in internal diagnostics with review_required; failed calls remain pending. Explicit development-mode rules do not constitute live validation.
7. Large-case storage scaling and durable distributed orchestration remain outside this phase; no claim of production hardening is made.

## Reproduction and local persistence

From the repository root, using the project virtual environment:

```
python scripts/setup-input-ocr.py
python -m unittest backend.tests.test_common_input backend.tests.test_security_hotfix -v
python scripts/validate-phase1-input.py --live
npm run test:backend
npm run build --prefix frontend
npm test
```

`--live` deliberately permits Bedrock inference on fictional input. It never creates a production case. The file checks use the user's existing Tamil PDF/image in `output/pdf/tamil-test-inputs`; these originals remain untracked and unchanged.

For an explicitly selected local-persistence/live-service development run, the existing factory supports USE_MOCK_AWS=true, USE_REAL_DATABASE=false, USE_REAL_STORAGE=true, USE_REAL_LLM=true; it reports hybrid mode. Set these in the process environment, not in a committed secrets file. This was not enabled on the user's running app automatically. The factory and DynamoDB interfaces remain unchanged.

## Files changed

Backend: backend/models/input.py; backend/services/input_canonical.py; backend/services/input_declarations.py; backend/services/input_layer.py; backend/services/ingestion.py; backend/routes/cases.py; backend/services/overview.py; backend/lambda_handler.py; backend/requirements.txt.

Frontend: frontend/src/api.js; frontend/src/pages/CommonInputPage.jsx.

Tests/fixtures: backend/tests/test_common_input.py; backend/tests/fixtures/tamil_refrigerator.txt; tests/redesign/input.spec.js; tests/redesign/workflow.spec.js.

Validation/setup/reporting: scripts/setup-input-ocr.py; scripts/validate-phase1-input.py; artifacts/phase1_input_validation.json; docs/phase1-input-report.md.

Stop after this Phase 1 delivery. Phase 2 requires explicit approval.
