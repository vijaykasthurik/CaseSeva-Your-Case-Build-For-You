"""Focused pending-source validation; optional RTI Phase 4 component calls.

Does not rerun Phase 3 or modify the saved Tamil understanding/team/issues.
Real legal acceptance stays blocked until an independent admin reviews sources.
"""
import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.adapters.mock.database import MockDatabaseAdapter
from backend.services.verified_corpus import VerifiedCorpus
from backend.services.legal_checks import LegalChecks
from backend.models.case import utc_now


def check_issues(corpus, issues, facts):
    checks, results = LegalChecks(None, corpus), {}
    for iid, issue in issues.items():
        if issue.get('superseded'):
            continue
        values = {'legal_issues.' + iid: issue, **{'facts.' + fid: fact for fid, fact in facts.items()}}
        values.update(checks.retrieval(iid)({'inputs': values}).outputs)
        values.update(checks.temporal(iid)({'inputs': values}).outputs)
        citation = checks.citation(iid)({'inputs': values}).outputs['citation_verification.' + iid]
        results[iid] = {'domain': issue['domain'], 'jurisdiction': issue.get('jurisdiction'),
            'candidate_ids': [v['source_id'] for v in values['legal_sources.candidates.' + iid]['candidates']],
            'citations': citation, 'temporal': values['temporal_findings.' + iid]}
        if any(d['status'] == 'VERIFIED' for d in citation['decisions']):
            raise ValueError('This pending-only check must not establish law')
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live-rti', action='store_true')
    args = parser.parse_args()
    folder = ROOT / '.localdev/phase4-authority-review'
    db = MockDatabaseAdapter(folder / 'database.json')
    corpus = VerifiedCorpus(db)
    detail = json.loads((ROOT / '.localdev/phase4-live/tamil-details.json').read_text(encoding='utf-8'))
    board = detail['board']
    report = {'checked_at': utc_now(), 'state': 'REVIEW_REQUIRED', 'source_verified_count': 0,
        'consumer': {'phase3_rerun': False, 'team_reused': list(board['data']['agent_team']['selected']),
            'case_file_produced': False, 'issues': check_issues(corpus, board['data']['legal_issues'], board['data']['facts'])},
        'corpus': corpus.readiness(), 'bedrock_calls_this_run': 0}
    # Probe domain filtering without inventing a location in the undated RTI case.
    report['domain_filter_probe'] = {
        domain: [s['source_id'] for s in corpus.search(domain, 'IN', 'information request consumer goods')]
        for domain in ('CONSUMER', 'RTI_ADMINISTRATIVE')}
    assert all(s.startswith('rti') for s in report['domain_filter_probe']['RTI_ADMINISTRATIVE'])
    assert all(s.startswith('cpa') for s in report['domain_filter_probe']['CONSUMER'])
    if args.live_rti:
        from dotenv import load_dotenv
        load_dotenv(ROOT / '.env')
        from backend.adapters.real.llm import RealLLMAdapter
        from backend.services.legal_team import LegalTeamAgents
        from backend.services.input_layer import build_raw_package
        # Exact existing cross-domain fixture, not a new legal answer fixture.
        import runpy
        fixtures = runpy.run_path(str(ROOT / 'scripts/validate-phase3-router.py'))['CASES']
        story = next(story for name, story, domain in fixtures if name == 'rti')
        routing = json.loads((ROOT / 'artifacts/phase3_router_validation.json').read_text(encoding='utf-8'))
        domain = next(r['output'] for r in routing['results'] if r['case'] == 'rti' and r['passed'])
        provider = RealLLMAdapter()
        class Budget:
            calls = 0
            def generate(self, prompt, schema):
                if not schema['stage'].startswith('foundation_') or self.calls >= 7:
                    raise ValueError('Focused Phase 4 component budget reached')
                self.calls += 1
                return provider.generate(prompt, schema)
        budget = Budget()
        cid = 'fictional-rti-phase4-' + uuid4().hex[:8]
        case = {'id': cid, 'case_id': cid, 'input_version': 1, 'client_story': story, 'evidence': []}
        case['raw_package'] = build_raw_package(case, SimpleNamespace(mode='mock'), working_language_required=False)
        db.create('cases', case)
        agents = LegalTeamAgents(SimpleNamespace(database=db, llm=budget, mode='hybrid'))
        facts = {'F001': {'fact_id': 'F001', 'proposition': story, 'certainty': 'STATED',
            'date': {'normalized': None, 'precision': 'UNKNOWN'}, 'evidence_ids': [], 'superseded': False}}
        values = {'facts': facts, 'parties': {}, 'input.evidence_ids': [], 'domain_classification': domain,
            'legal_capabilities': {'blockers': ['INDEPENDENT_AUTHORITY_REVIEW_PENDING']}}
        claim = {'case_id': cid, 'execution_id': 'phase4-component-' + uuid4().hex,
            'inputs': values, 'previous_outputs': {}}
        report['second_domain'] = {'case_id': cid, 'scope': 'Live Phase 4 components over authored existing RTI premise; no full Phase 3 case reconstruction'}
        try:
            values.update(agents.team(claim).outputs)
            for name in values['agent_team']['selected']:
                values.update(agents.specialist(name)(claim).outputs)
            result = agents.issues(claim)
            issues = result.outputs['legal_issues']
            report['second_domain'].update(team=list(values['agent_team']['selected']),
                issues=check_issues(corpus, issues, facts), source_verified=False, case_file_produced=False)
            (folder / 'rti-components.json').write_text(json.dumps({'inputs': values, 'outputs': result.outputs}, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception as error:
            report['second_domain'].update(state='BLOCKED', failure_type=type(error).__name__)
            raise
        finally:
            report.update(bedrock_calls_this_run=budget.calls, bedrock_input_tokens=provider.total_input_tokens,
                          bedrock_output_tokens=provider.total_output_tokens)
            (folder / 'rti-provider-logs.json').write_text(json.dumps(provider.stage_logs, ensure_ascii=False, indent=2), encoding='utf-8')
            (ROOT / 'artifacts/phase4_pending_authority_validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    else:
        (ROOT / 'artifacts/phase4_pending_authority_validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'state': report['state'], 'bedrock_calls': report['bedrock_calls_this_run'], 'consumer_issues': len(report['consumer']['issues'])}))


if __name__ == '__main__':
    main()
