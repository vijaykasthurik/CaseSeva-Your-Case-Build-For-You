"""Phase 4 dispatch continuation, using the existing Blackboard scheduler only."""
import logging
import time
from uuid import uuid4
from .case_blackboard import CaseBlackboard, invalidate, SnapshotCapacityExceeded
from .orchestrator import MasterLegalOrchestrator
from .verified_corpus import VerifiedCorpus
from .legal_registry import legal_registry
from .core_workflow import run_core, prepare
from .legal_artifacts import compact_specialists

CORE_NAMES = {'CASE_ISSUES', 'CASE_STAGE', 'FACT_TIMELINE', 'PARTY_RELATIONSHIP', 'EVIDENCE_MAPPING', 'CLARIFICATION', 'RECONCILIATION', 'DOMAIN_ROUTER'}


def run_plan(db, adapters, corpus, case_id, targets, board, deadline):
    registry, _ = legal_registry(adapters, corpus, board)
    controller = MasterLegalOrchestrator(db, registry, capabilities=('core_reasoning', 'legal_reasoning'))
    controller.start(case_id, targets, replace_plan=True)
    for _ in range(32):
        if time.monotonic() >= deadline:
            break
        board = controller.tick(case_id)
        active = [n for n in board['nodes'].values() if not n.get('inactive')]
        if any(n.get('failure_reason') == 'SnapshotCapacityExceeded' for n in active):
            raise SnapshotCapacityExceeded('Phase 4 output requires capacity review')
        retry = [n for n in active if n['status'] == 'FAILED' and n.get('transient') and n['attempts'] <= n['contract']['max_retries']]
        if not any(n['status'] in {'READY', 'RUNNING'} for n in active) and not retry:
            break
        if retry:
            time.sleep(min(2, max(0, min(n.get('next_retry_at', 0) for n in retry) - time.time())))
    return board


def assemble_case_file(db, case_id, board, corpus):
    foundation = board['data']['legal_foundation']
    if foundation['status'] != 'SOURCE_VERIFIED' or any(c for c in board['conflicts'].values() if not c['resolution']):
        return None
    from .case_file import assemble_canonical_case_file
    return assemble_canonical_case_file(db, case_id, board, corpus,
                                        pipeline_status='ENGINE1_CASE_FILE_READY')


def run_legal_foundation(app, case_id):
    db, adapters = app.state.adapters.database, app.state.adapters
    store = CaseBlackboard(db)
    case = db.get('cases', case_id)
    if not case or not case.get('legal_foundation_requested'):
        return
    # Phase 3 owns original input synchronization and preserves its live gate.
    board = store.sync_input(case_id)
    core_ready = all(board['nodes'].get(n, {}).get('status') == 'COMPLETED' for n in CORE_NAMES)
    raw = case.get('raw_package') or {}
    if not core_ready or raw.get('input_version') != case.get('input_version', 1):
        run_core(app, case_id)
        board = store.read_board(case_id)
        if not all(board['nodes'].get(n, {}).get('status') == 'COMPLETED' for n in CORE_NAMES):
            return
    token, now = uuid4().hex, time.time()
    if not db.get('core_workers', case_id):
        try:
            db.create('core_workers', {'id': case_id, 'token': None, 'lease_until': 0})
        except ValueError:
            pass
    reservation = db.mutate('core_workers', case_id, lambda c: {} if c.get('token') and c['lease_until'] > now else {'token': token, 'lease_until': now + 900})
    if reservation.get('token') != token:
        return
    corpus = getattr(adapters, 'verified_corpus', None) or VerifiedCorpus(db)
    try:
        _, board = prepare(app, case_id)
        if not all(board['nodes'].get(n, {}).get('status') == 'COMPLETED' for n in CORE_NAMES):
            db.update('cases', case_id, {'status': 'REVIEW_REQUIRED', 'legal_foundation_status': 'REVIEW_REQUIRED'})
            return
        deadline = time.monotonic() + 600
        board = compact_specialists(db, store, case_id, board)
        corpus = getattr(adapters, 'verified_corpus', None) or VerifiedCorpus(db)
        db.update('cases', case_id, {'status': 'LEGAL_FOUNDATION_IN_PROGRESS', 'legal_foundation_status': 'IN_PROGRESS',
                                   'current_stage': None, 'stage_statuses': {}, 'processing_error': None,
                                   'legal_capacity_review_required': False,
                                   'legal_case_file_current': False})
        if db.get('cases', case_id).get('legal_retry_requested'):
            def retry_failed(checkpoint):
                for name, node in checkpoint['nodes'].items():
                    if name not in CORE_NAMES and (node['status'] == 'FAILED' or node.get('agent_blocked')):
                        invalidate(checkpoint, node['contract']['writes'], exclude=(name,))
                        node.update(status='STALE', stale=True, agent_blocked=False, claim_token=None,
                                    review_generation=node.get('review_generation', 0) + 1)
            store.change(case_id, retry_failed, kind='LEGAL_RETRY_REQUESTED')
            db.update('cases', case_id, {'legal_retry_requested': False})
        changes = {'legal_capabilities': {'retrieval': 'VERSIONED_PRIMARY_SOURCES', 'blockers': []},
                   'understanding_reference': db.get('cases', case_id).get('understanding_snapshot') or {'board_version': board['version']}}
        if 'legal_context' not in board['data']:
            changes['legal_context'] = {}
        store.append_change(case_id, changes, actor='system', reason='Phase 4 capabilities and understanding version')
        board = run_plan(db, adapters, corpus, case_id, ['TEAM_BUILDER'], store.read_board(case_id), deadline)
        if board['nodes']['TEAM_BUILDER']['status'] != 'COMPLETED':
            db.update('cases', case_id, {'status': 'LEGAL_FOUNDATION_REVIEW_REQUIRED', 'legal_foundation_status': 'REVIEW_REQUIRED'})
            return
        _, plan = legal_registry(adapters, corpus, board)
        board = run_plan(db, adapters, corpus, case_id, [plan['issues']], board, deadline)
        if board['nodes'][plan['issues']]['status'] != 'COMPLETED':
            db.update('cases', case_id, {'status': 'LEGAL_FOUNDATION_REVIEW_REQUIRED', 'legal_foundation_status': 'REVIEW_REQUIRED'})
            return
        additions = {'limitation_triggers.' + iid: {} for iid, issue in board['data']['legal_issues'].items()
                     if not issue.get('superseded') and iid not in board['data'].get('limitation_triggers', {})}
        if additions:
            store.append_change(case_id, additions, actor='system', reason='Unresolved legal trigger review checkpoints')
        board = corpus.sync_case(case_id)
        _, plan = legal_registry(adapters, corpus, board)
        board = run_plan(db, adapters, corpus, case_id, [plan['foundation']], board, deadline)
        node = board['nodes'][plan['foundation']]
        foundation = board['data'].get('legal_foundation', {}) if node['status'] == 'COMPLETED' else {}
        if foundation.get('status') == 'SOURCE_VERIFIED':
            case_file = assemble_case_file(db, case_id, board, corpus)
            canonical = case_file
        else:
            case_file = None
            from .case_file import assemble_canonical_case_file
            canonical = assemble_canonical_case_file(db, case_id, board, corpus, pipeline_status=
                'LEGAL_CORPUS_NOT_READY' if not corpus.sources() else 'LEGAL_FOUNDATION_REVIEW_REQUIRED')
        status = 'ENGINE1_CASE_FILE_READY' if case_file else 'LEGAL_CORPUS_NOT_READY' if not corpus.sources() else 'LEGAL_FOUNDATION_REVIEW_REQUIRED'
        update = {'status': status, 'legal_foundation_status': canonical['legal_foundation_status'],
                  'legal_foundation_snapshot': {'board_version': board['version'], 'status': foundation.get('status', 'REVIEW_REQUIRED')},
                  'canonical_case_file': canonical,
                  'current_stage': None, 'stage_statuses': {}}
        if case_file:
            store.record_case_file(case_id, {'case_file_version': case_file['version'], 'board_version': board['version'],
                'input_version': case_file['input_version'], 'dependency_versions': case_file['dependency_versions'],
                'generated_at': case_file['created_at'], 'status': 'CURRENT'})
            update['case_file'] = case_file
            update['legal_case_file_current'] = True
        def publish(current):
            if current.get('input_version', 1) != board['data']['input']['input_version']:
                raise ValueError('Input changed during legal publication')
            return update
        db.mutate('cases', case_id, publish)
    except SnapshotCapacityExceeded:
        db.update('cases', case_id, {'status': 'LEGAL_FOUNDATION_REVIEW_REQUIRED', 'legal_foundation_status': 'REVIEW_REQUIRED',
            'legal_case_file_current': False, 'legal_capacity_review_required': True,
            'processing_error': {'engine': 1, 'message': 'This case needs review before legal processing can continue. Saved information is preserved.'}})
    except Exception:
        logging.getLogger(__name__).exception('Legal foundation worker requires review: %s', case_id)
        db.update('cases', case_id, {'status': 'LEGAL_FOUNDATION_REVIEW_REQUIRED', 'legal_foundation_status': 'REVIEW_REQUIRED',
                                   'processing_error': {'engine': 1, 'message': 'Legal verification could not finish. Saved information is preserved.'}})
    finally:
        current = db.get('cases', case_id)
        if current.get('status') == 'LEGAL_FOUNDATION_REVIEW_REQUIRED':
            from .case_file import assemble_canonical_case_file
            latest = store.read_board(case_id)
            if (latest.get('data', {}).get('facts')
                    and current.get('canonical_case_file', {}).get('stage_provenance', {}).get('board_version') != latest['version']):
                assemble_canonical_case_file(db, case_id, latest, corpus,
                                             pipeline_status=current['status'])
        db.mutate('core_workers', case_id, lambda current: {'token': None, 'lease_until': 0} if current.get('token') == token else {})
