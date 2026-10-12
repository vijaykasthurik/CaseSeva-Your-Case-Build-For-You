"""Opt-in, bounded live checks using recorded fictional Phase 3 understanding.

No DynamoDB, Transcribe, infrastructure writes or production case mutation.
Downloaded sources remain PENDING until independent ingestion review.
"""
import argparse
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--language', choices=['english', 'tamil'], default='tamil')
    parser.add_argument('--source-only', action='store_true')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    if not args.live:
        raise SystemExit('Use --live for the approved, bounded external validation')
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env')
    from backend.models.case import utc_now
    from backend.adapters.real.official_sources import OfficialSourceAdapter
    folder = ROOT / '.localdev' / 'phase4-live'
    folder.mkdir(parents=True, exist_ok=True)
    report_path = ROOT / 'artifacts' / 'phase4_live_validation.json'
    report = json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else {}
    report.update(scope='Fictional cases only; local persistence; bounded Bedrock and official-source HTTP', timestamp=utc_now(),
                  persistence='LOCAL VALIDATED — DYNAMODB LIVE ACCESS BLOCKED BY AWS SCP', transcribe='BLOCKED BY AWS SCP — NOT RETRIED')
    if 'official_source' not in report:
        try:
            downloaded = OfficialSourceAdapter().fetch('india_code', 'https://www.indiacode.nic.in/bitstream/123456789/15256/1/a2019-35.pdf')
            (folder / 'official-discovery.json').write_text(json.dumps(downloaded, ensure_ascii=False, indent=2), encoding='utf-8')
            report['official_source'] = {k: v for k, v in downloaded.items() if k != 'official_text'}
            report['official_source'].update(characters=len(downloaded['official_text']), connectivity='LIVE VALIDATED', authority='PENDING_INGESTION_REVIEW')
        except Exception as error:
            report['official_source'] = {'connectivity': 'BLOCKED', 'failure_type': type(error).__name__, 'authority': 'NOT_VERIFIED'}
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.source_only:
        print(json.dumps(report, ensure_ascii=True))
        return
    from backend.adapters.real.llm import RealLLMAdapter
    from backend.adapters.mock.database import MockDatabaseAdapter
    from backend.services.case_blackboard import CaseBlackboard
    from backend.services.legal_workflow import run_legal_foundation
    detail = json.loads((ROOT / '.localdev' / 'phase3-live' / (args.language + '-details.json')).read_text(encoding='utf-8'))
    db_path = folder / (args.language + '-' + uuid4().hex[:8] + '.json')
    if args.resume:
        candidates = [p for p in folder.glob(args.language + '-*.json') if len(p.stem.removeprefix(args.language + '-')) == 8]
        db_path = max(candidates, key=lambda p: p.stat().st_mtime)
    db = MockDatabaseAdapter(db_path)
    case, board = detail['case'], detail['board']
    if not all(n['status'] == 'COMPLETED' for n in board['nodes'].values()):
        raise SystemExit('Recorded core understanding is incomplete; refusing paid rerun')
    if args.resume:
        db.update('cases', case['case_id'], {'legal_retry_requested': True})
    else:
        case.update(legal_foundation_requested=True)
        db.create('cases', case)
        db.create('case_board_snapshots', {'id': 'imported-fictional-core', 'case_id': case['case_id'], 'board': board, 'previous': None,
            'event': {'type': 'IMPORTED_FICTIONAL_VALIDATION', 'timestamp': utc_now()}})
        db.create('case_board_heads', {'id': case['case_id'], 'version': board['version'], 'snapshot_id': 'imported-fictional-core'})
    provider = RealLLMAdapter()
    class BudgetedModel:
        def __init__(self):
            self.calls = 0
        def generate(self, prompt, schema):
            if not schema['stage'].startswith('foundation_'):
                raise RuntimeError('Phase 3 paid rerun is outside this validation budget')
            if self.calls >= 8:
                raise RuntimeError('Focused validation provider-call budget exhausted')
            self.calls += 1
            return provider.generate(prompt, schema)
    model = BudgetedModel()
    adapters = SimpleNamespace(database=db, llm=model, mode='hybrid')
    started = time.monotonic()
    print('Running focused fictional Phase 4:', args.language, flush=True)
    run_legal_foundation(SimpleNamespace(state=SimpleNamespace(adapters=adapters)), case['case_id'])
    result = db.get('cases', case['case_id'])
    board = CaseBlackboard(db).read_board(case['case_id'])
    summary = {'case_status': result['status'], 'model': provider.model_id, 'calls': model.calls,
        'input_tokens': provider.total_input_tokens, 'output_tokens': provider.total_output_tokens,
        'seconds': round(time.monotonic() - started, 1), 'core_reused': True, 'resumed': args.resume,
        'agents': {name: {'status': node['status'], 'failure': node.get('failure_reason')} for name, node in board['nodes'].items() if not node.get('inactive')},
        'selected_specialists': list(board['data'].get('agent_team', {}).get('selected', {})),
        'issues': len(board['data'].get('legal_issues', {})), 'case_file_created': bool(result.get('case_file')),
        'legal_corpus_ready': False, 'legal_foundation_status': result.get('legal_foundation_status')}
    if args.language in report.get('cases', {}):
        report.setdefault('prior_runs', []).append({'language': args.language, **report['cases'][args.language]})
    report.setdefault('cases', {})[args.language] = summary
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (folder / (args.language + '-details.json')).write_text(json.dumps({'case': result, 'board': board, 'logs': provider.stage_logs}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()
