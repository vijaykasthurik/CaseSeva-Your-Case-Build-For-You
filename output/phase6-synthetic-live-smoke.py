import os, sys, json, time, hashlib
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv('.env')

name = 'caseseva_test_phase6_live_' + uuid4().hex
os.environ.update(
    MONGODB_DATABASE=name,
    DATABASE_PROVIDER='mongodb',
    OBJECT_STORE_PROVIDER='mongodb',
    USE_MOCK_AWS='false',
    USE_REAL_LLM='true',
    LLM_PROVIDER='bedrock',
    WORKFLOW_PROVIDER='mock',
    EMAIL_PROVIDER='disabled',
    MEDIA_PROVIDER='mock'
)
os.environ.pop('AWS_LAMBDA_FUNCTION_NAME', None)

from fastapi.testclient import TestClient
from backend.main import app
from backend.database.mongo_client import get_mongo_client
from backend.services.case_blackboard import CaseBlackboard
from backend.models.case_file import CanonicalCaseFile
from backend.models.engines import CaseChallengeReport

mongo = get_mongo_client('mongodb://127.0.0.1:27017')
protected = (
    'legal_authority_heads', 'legal_authority_versions', 'legal_authority_reviews',
    'legal_review_submissions', 'legal_revision_requests'
)
for collection in protected:
    rows = list(mongo.caseseva[collection].find({}))
    if rows:
        mongo[name][collection].insert_many(rows)

report = {'database': name, 'provider': 'real configured LLM', 'test_double': False}

try:
    with TestClient(app) as client:
        def call(method, path, **kw):
            r = client.request(method, path, **kw)
            if r.status_code >= 400:
                raise RuntimeError(str((path, r.status_code, r.text[:400])))
            return r.json()

        # Step 1: Citizen signup & create consultation
        account = call('POST', '/api/auth/signup', json={
            'full_name': 'Synthetic Laptop Citizen Phase6',
            'email': 'phase6-' + uuid4().hex + '@example.test',
            'password': uuid4().hex,
            'mobile_number': '9876543210',
            'preferred_language': 'English',
            'state': 'Tamil Nadu',
            'district_city': 'Chennai',
            'role': 'client'
        })
        h = {'Authorization': 'Bearer ' + account['session_token']}
        cid = call('POST', '/api/cases', headers=h)['case']['case_id']
        report['case_id'] = cid

        story = (
            'I am a fictional customer in Chennai. On 1 September 2026 I paid Rs. 54,999 to Example Laptop Store '
            'for a laptop for personal use. It was delivered on 3 September 2026 with a cracked display and broken bezel. '
            'On 4 September I emailed the seller photographs of the damage. On 5 September the seller promised replacement '
            'within seven days. No replacement arrived by 20 September, and the seller stopped answering. I seek replacement '
            'or refund. I have not filed any complaint or court case. The invoice and support email are uploaded; payment proof '
            'and delivery photographs are not currently available.'
        )
        call('PATCH', '/api/cases/' + cid, headers=h, json={'stage': 'NEW_CONSULTATION', 'client_story': story})

        uploaded = []
        for filename, content in [
            ('invoice.txt', b'SYNTHETIC TEST INVOICE: Example Laptop Store. Laptop for personal use. Paid Rs. 54,999 on 1 September 2026. Chennai.'),
            ('support_email.txt', b'SYNTHETIC SUPPORT EMAIL: 5 September 2026. Example Laptop Store acknowledges the cracked display reported on 4 September and promises replacement within seven days.')
        ]:
            e = call('POST', '/api/cases/' + cid + '/evidence', headers=h, files={'file': (filename, content, 'text/plain')})['evidence']
            uploaded.append((e['evidence_id'], hashlib.sha256(content).hexdigest()))

        # Step 2: Core Understanding
        call('POST', '/api/cases/' + cid + '/core-understanding', headers=h)
        db = app.state.adapters.database

        def wait():
            for _ in range(360):
                c = db.get('cases', cid)
                worker = db.get('core_workers', cid) or {}
                if c['status'] not in ('ENGINE1_RUNNING', 'LEGAL_FOUNDATION_IN_PROGRESS', 'ENGINE2_RUNNING') and not worker.get('token'):
                    return c
                time.sleep(2)
            raise RuntimeError('Application processing timed out')

        c = wait()
        print('CORE COMPLETE, status:', c['status'], flush=True)

        if c['status'] == 'AWAITING_CLIENT_INFO':
            rounds = c.get('clarification_rounds', [])
            if rounds and rounds[-1]['status'] == 'WAITING':
                batch = rounds[-1]
                answers = [{'question_id': q['question_id'], 'response': 'NOT_AVAILABLE', 'value': ''} for q in batch['questions']]
                call('POST', f'/api/cases/{cid}/clarifications', headers=h, json={'answers': answers})
                c = wait()
                print('AFTER CLARIFICATION COMPLETE, status:', c['status'], flush=True)

        if c['status'] in ('CASE_UNDERSTANDING_READY', 'REVIEW_REQUIRED'):
            call('POST', '/api/cases/' + cid + '/legal-foundation', headers=h)
            c = wait()
            print('LEGAL FOUNDATION COMPLETE, status:', c['status'], flush=True)

        f = c.get('canonical_case_file') or {}
        CanonicalCaseFile.model_validate(f)
        engine1_version = f['version']
        print(f"Engine 1 Canonical Case File v{engine1_version} ready. Legal status: {f['legal_foundation_status']}", flush=True)

        # Step 3: Citizen chooses "Strengthen My Case" (Engine 2)
        e2_choice = call('POST', f'/api/cases/{cid}/engine2', headers=h, json={'run': True})
        print("Engine 2 dispatched, choice status:", e2_choice, flush=True)

        c = wait()
        print("Engine 2 complete, status:", c['status'], "processing_error:", c.get('processing_error'), flush=True)

        # Step 4: Verify outputs and persistence
        e2_reports = [r for r in db.list('engine2_challenge_reports') if r.get('case_id') == cid]
        if not e2_reports:
            raise RuntimeError("No report in engine2_challenge_reports!")

        latest_record = e2_reports[-1]
        raw_report = latest_record['report']
        challenge_report = CaseChallengeReport.model_validate(raw_report)

        overview = call('GET', f'/api/cases/{cid}/client-case-overview', headers=h)['overview']

        # Count applicable law added by Engine 2
        engine2_provisions_added = sum(len(a.provision_ids) for a in challenge_report.opposing_arguments)

        report.update({
            'engine1_case_file_version': engine1_version,
            'bound_engine1_case_file_version': challenge_report.engine1_case_file_version,
            'engine2_run_id': challenge_report.engine2_run_id,
            'engine2_version': challenge_report.version,
            'legal_foundation_status': f['legal_foundation_status'],
            'challenge_perspectives': challenge_report.challenge_perspectives,
            'opposing_arguments_count': len(challenge_report.opposing_arguments),
            'factual_weaknesses_count': len(challenge_report.factual_weaknesses),
            'evidence_gaps_count': len(challenge_report.evidence_gaps),
            'contradictions_count': len(challenge_report.contradictions),
            'procedural_risks_count': len(challenge_report.procedural_risks),
            'unresolved_assumptions_count': len(challenge_report.unresolved_assumptions),
            'legal_authority_limitations': challenge_report.legal_authority_limitations,
            'preparation_actions': challenge_report.preparation_actions,
            'engine2_provisions_added': engine2_provisions_added,
            'engine2_stale': overview.get('engine2_stale'),
            'argument_analysis_run': overview.get('argument_analysis_run'),
            'argument_analysis_note': overview.get('argument_analysis_note'),
            'overview_key_challenges': overview.get('key_challenges'),
            'overview_evidence_gaps': overview.get('evidence_gaps'),
            'overview_preparation_actions': overview.get('preparation_actions'),
            'engine1_case_file_mutated': c.get('canonical_case_file') != f,
            'report_sample': {
                'opposing_arguments': [a.model_dump() for a in challenge_report.opposing_arguments[:2]],
                'factual_weaknesses': [w.model_dump() for w in challenge_report.factual_weaknesses[:2]],
                'evidence_gaps': [g.model_dump() for g in challenge_report.evidence_gaps[:2]],
                'procedural_risks': [r.model_dump() for r in challenge_report.procedural_risks[:2]],
            }
        })

        report['acceptance_passed'] = (
            challenge_report.engine1_case_file_version == engine1_version
            and not report['engine1_case_file_mutated']
            and engine2_provisions_added == 0
            and len(challenge_report.challenge_perspectives) > 0
            and len(challenge_report.opposing_arguments) > 0
            and len(challenge_report.factual_weaknesses) > 0
            and len(challenge_report.evidence_gaps) > 0
            and len(challenge_report.legal_authority_limitations) > 0
            and overview.get('argument_analysis_run') is True
            and overview.get('engine2_stale') is False
        )

        print("\n=== PHASE 6 SYNTHETIC LIVE SMOKE RESULT ===")
        print(json.dumps({
            'case_id': cid,
            'engine1_case_file_version': engine1_version,
            'bound_engine1_case_file_version': challenge_report.engine1_case_file_version,
            'legal_foundation_status': f['legal_foundation_status'],
            'engine2_provisions_added': engine2_provisions_added,
            'argument_analysis_run': overview.get('argument_analysis_run'),
            'engine2_stale': overview.get('engine2_stale'),
            'acceptance_passed': report['acceptance_passed'],
        }, indent=2), flush=True)

finally:
    Path('output/phase6-synthetic-live-smoke.json').write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
    mongo.drop_database(name)
