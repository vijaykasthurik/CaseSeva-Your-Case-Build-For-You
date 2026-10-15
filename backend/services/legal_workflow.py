"""Phase 4 dispatch continuation, using the existing Blackboard scheduler only."""
import logging
import time
from uuid import uuid4
from .case_blackboard import CaseBlackboard, versions, invalidate, SnapshotCapacityExceeded
from .orchestrator import MasterLegalOrchestrator
from .verified_corpus import VerifiedCorpus
from .legal_registry import legal_registry
from .core_workflow import run_core, prepare
from .legal_artifacts import compact_specialists
from .legal_visibility import authority_manifest
from ..models.case import utc_now

CORE_NAMES = {'CASE_STAGE', 'FACT_TIMELINE', 'PARTY_RELATIONSHIP', 'EVIDENCE_MAPPING', 'CLARIFICATION', 'RECONCILIATION', 'DOMAIN_ROUTER'}


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
    data = board['data']
    case = db.get('cases', case_id)
    if case.get('input_version', 1) != data['input']['input_version']:
        raise ValueError('Input changed before Case File assembly')
    current = case.get('case_file') or {}
    dependencies = versions(board, ('facts', 'parties', 'timeline', 'incidents', 'input', 'domain_classification', 'evidence_mapping',
        'agent_team', 'legal_issues', 'legal_sources', 'citation_verification', 'temporal_findings', 'jurisdiction_remedy', 'limitation', 'legal_foundation'))
    for finding in foundation['findings'].values():
        if finding['status'] != 'SOURCE_VERIFIED' or not finding['verified_source_ids']:
            raise ValueError('Case File lacks complete verified-source coverage')
    laws = {}
    for iid in foundation['findings']:
        for app in data['legal_applications'][iid]['applications']:
            source = corpus.get(app['source_id'])
            if not source or source['version_id'] != app['source_version'] or not corpus.validate_source({k: v for k, v in source.items() if k != 'version_id'})[0]:
                raise ValueError('Authority changed before Case File assembly')
            laws[app['source_id']] = {'provision_id': app['source_id'], 'title': source['title'], 'section': source['section'],
                'citation': source.get('citation'), 'source_url': source['official_url'], 'retrieved_at': source['retrieved_at'],
                'verification_status': 'VERIFIED', 'authority_status': 'VERIFIED_AUTHORITY',
                'source_version': source['version_id'], 'explanation': 'Official source checked. Its application to your case requires advocate review.'}
    authority_versions = authority_manifest(corpus, laws)
    if current.get('dependency_versions') == dependencies and current.get('authority_versions') == authority_versions:
        return current
    from .case_file import (
        compact_timeline, compact_parties, compact_relationships,
        compact_evidence_mappings, compact_clarification, compact_issues,
        build_citizen_summary, build_safe_next_actions
    )
    raw = case.get('raw_package') or {}
    evidence_inventory = [
        {'evidence_id': item.get('evidence_id'), 'filename': item.get('filename'),
         'content_type': item.get('content_type'), 'size': item.get('size'),
         'description': item.get('description', ''), 'readable': item.get('extraction', {}).get('status') == 'COMPLETED'}
        for item in case.get('evidence', [])
    ]
    missing_evidence = list(raw.get('unavailable_evidence', [])) + [f"Item: {u}" for u in raw.get('unknown_evidence', [])]
    specialist_outputs = [
        {'specialist': sname, 'agent': sdata.get('agent', sname), 'domain': sdata.get('domain', ''),
         'observations': sdata.get('observations', []), 'issue_families': sdata.get('issue_families', [])}
        for sname, sdata in data.get('specialists', {}).items() if isinstance(sdata, dict)
    ]
    facts_list = [{'fact_id': k, 'text': v['proposition'], 'proposition': v['proposition'], 'source_status': 'UNVERIFIED', 'certainty': v.get('certainty', 'STATED'), 'category': v.get('category', 'GENERAL'), 'date': v.get('date'), 'exact_values': v.get('exact_values', []), 'evidence_ids': v.get('evidence_ids', [])} for k, v in data['facts'].items() if not v.get('superseded')]
    domain_info = data.get('domain_classification', {})
    summary = build_citizen_summary(case.get('client_story', ''), facts_list, domain_info)
    next_actions = build_safe_next_actions('VERIFIED_AUTHORITY', missing_evidence)

    result = {'version': current.get('version', 0) + 1, 'case_file_version': current.get('version', 0) + 1,
        'kind': 'SOURCE_VERIFIED_ENGINE1', 'created_at': utc_now(),
        'case_id': case_id,
        'original_narrative': case.get('client_story', ''),
        'normalized_narrative': data.get('input', {}).get('canonical_narrative') or case.get('client_story', ''),
        'authority_versions': authority_versions,
        'authority_provenance': authority_versions,
        'input_version': case.get('input_version', 1), 'board_version': board['version'],
        'understanding_reference': data['understanding_reference'], 'dependency_versions': dependencies,
        'foundation_complete': True, 'review_state': 'ADVOCATE_REVIEW_REQUIRED',
        'intake': {'narrative': case.get('client_story', '')},
        'facts': facts_list,
        'disputed_facts': [f for f in facts_list if f.get('certainty') in {'CONFLICTED', 'UNKNOWN'}],
        'timeline': compact_timeline(data.get('timeline', {}), data.get('incidents', {})),
        'parties': compact_parties(data.get('parties', {})),
        'relationships': compact_relationships(data.get('relationships', {})),
        'evidence_inventory': evidence_inventory,
        'evidence_mappings': compact_evidence_mappings(data.get('evidence_mapping', {})),
        'missing_evidence': missing_evidence,
        'missing_information': missing_evidence,
        'clarification_questions': compact_clarification(case.get('clarification_rounds', [])),
        'issues': compact_issues(data.get('legal_issues', {})),
        'domains': domain_info,
        'specialist_outputs': specialist_outputs,
        'applicable_law': list(laws.values()),
        'legal_findings': list(laws.values()),
        'legal_foundation_status': 'VERIFIED_AUTHORITY',
        'unresolved_legal_requirements': [],
        'reconciliation': {'conflicts': list(board.get('conflicts', {}).values()), 'contested_claims': []},
        'citizen_safe_summary': summary,
        'next_actions': next_actions,
        'pipeline_status': 'ENGINE1_CASE_FILE_READY',
        'stage_provenance': {'board_version': board['version'], 'input_version': case.get('input_version', 1), 'dependency_versions': dependencies, 'created_at': utc_now()},
        'legal_foundation_reference': {'board_version': board['version'], 'path': 'legal_foundation'},
        'pending_advocate_verification': [{'type': 'legal_verification'}],
        'processing_mode': case.get('raw_package', {}).get('processing_mode')}
    snapshot_id = case_id + ':' + str(result['version'])
    existing = db.get('engine1_legal_case_files', snapshot_id)
    if existing:
        if existing['case_file']['dependency_versions'] != dependencies:
            raise ValueError('Case File version collision requires review')
        return existing['case_file']
    db.create('engine1_legal_case_files', {'id': snapshot_id, 'case_id': case_id, 'case_file': result})
    return result


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
            canonical = assemble_canonical_case_file(db, case_id, board, corpus)
        status = 'ENGINE1_CASE_FILE_READY' if case_file else 'LEGAL_CORPUS_NOT_READY' if not corpus.sources() else 'LEGAL_FOUNDATION_REVIEW_REQUIRED'
        update = {'status': status, 'legal_foundation_status': 'READY' if case_file else canonical.get('legal_foundation_status', 'REVIEW_REQUIRED'),
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
        db.mutate('core_workers', case_id, lambda current: {'token': None, 'lease_until': 0} if current.get('token') == token else {})
