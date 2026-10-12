"""Immutable large specialist results behind case-bound Blackboard references."""
from ..models.legal_foundation import SpecialistProposal
from .case_blackboard import digest, overlaps, set_values, value_at


def validate_specialist(value):
    if 'artifact_id' in value:
        if set(value) != {'agent', 'domain', 'legal_state', 'execution_id', 'artifact_id', 'content_hash', 'observation_count'}:
            raise ValueError('Invalid specialist reference contract')
        if value['legal_state'] != 'PENDING_SOURCE' or not isinstance(value['observation_count'], int):
            raise ValueError('Invalid specialist review state')
    else:
        SpecialistProposal.model_validate({k: v for k, v in value.items() if k not in {'agent', 'domain', 'legal_state', 'execution_id'}})
    return value


def save_specialist(db, case_id, value):
    validate_specialist(value)
    content_hash = digest(value)
    artifact_id = digest([case_id, value['agent'], content_hash])
    if not db.get('legal_specialist_artifacts', artifact_id):
        try:
            db.create('legal_specialist_artifacts', {'id': artifact_id, 'case_id': case_id, 'content_hash': content_hash, 'value': value})
        except ValueError:
            existing = db.get('legal_specialist_artifacts', artifact_id)
            if not existing or existing['value'] != value or existing['case_id'] != case_id:
                raise
    return {key: value[key] for key in ('agent', 'domain', 'legal_state', 'execution_id')} | {
        'artifact_id': artifact_id, 'content_hash': content_hash, 'observation_count': len(value['observations'])}


def load_specialist(db, case_id, reference):
    validate_specialist(reference)
    if 'artifact_id' not in reference:
        return reference
    record = db.get('legal_specialist_artifacts', reference['artifact_id'])
    if (not record or record['case_id'] != case_id or record['content_hash'] != reference['content_hash']
        or digest(record['value']) != reference['content_hash'] or record['value']['agent'] != reference['agent']):
        raise ValueError('Specialist artifact identity or integrity mismatch')
    validate_specialist(record['value'])
    return record['value']


def compact_specialists(db, store, case_id, board):
    changes = {}
    for name, value in board['data'].get('specialists', {}).items():
        path = 'specialists.' + name
        if 'artifact_id' in value or any(overlaps(path, p) for p in board['protected']):
            continue
        changes[path] = save_specialist(db, case_id, value)
    if not changes:
        return board
    def transform(current):
        safe = {path: ref for path, ref in changes.items()
                if not any(overlaps(path, p) for p in current['protected'])
                and value_at(current['data'], path) == value_at(board['data'], path)}
        paths, affected = set_values(current, safe)
        # The previous immutable snapshot retains full prior content; duplicating
        # it in the compaction event would defeat the snapshot-size bound.
        return {'changed_paths': paths, 'affected_outputs': affected, 'artifact_references': safe}
    return store.change(case_id, transform, actor='system', kind='SPECIALIST_REFERENCES_STORED',
                        reason='Preserve specialist results in immutable case artifacts')
