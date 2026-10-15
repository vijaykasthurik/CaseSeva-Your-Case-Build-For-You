"""Operator-only, audit-before-CAS platform administrator promotion.

Standalone stores commit access and its receipt together on the user. The
immutable per-user reservation survives crashes; ambiguous history is refused.
"""
import hashlib
import json
from uuid import uuid4

from ..models.case import utc_now


def _fingerprint(user):
    return hashlib.sha256(json.dumps(user, sort_keys=True, default=str,
                                    separators=(',', ':')).encode()).hexdigest()


def promote_existing_user_to_admin(db, email=None, *, user_id=None):
    if (email is None) == (user_id is None):
        raise ValueError('Specify exactly one existing account email or user ID.')
    if user_id is not None:
        matches = [u for u in db.list('users') if u.get('id') == user_id]
        if len(matches) != 1:
            raise ValueError('Exactly one existing account must match; no account was changed.')
        email = matches[0].get('email', '')
    normalized = email.strip().lower()

    def account():
        matches = [u for u in db.list('users')
                   if u.get('email', '').strip().lower() == normalized]
        if (not normalized or len(matches) != 1
                or (user_id is not None and matches[0].get('id') != user_id)):
            raise ValueError('Exactly one existing account must match; no account was changed.')
        return matches[0]

    user = account()
    if user.get('role') == 'admin':
        return {'status': 'already_admin', 'user_id': user['id']}
    if user.get('role') != 'client':
        raise ValueError('Only an existing client can be promoted; advocates require a separate platform-admin identity.')
    if user.get('admin_role_intent_id'):
        raise ValueError('Previously applied administrator intent conflicts with current role.')
    intents = [a for a in db.list('admin_role_audit') if a.get('user_id') == user['id']]
    if len(intents) > 1:
        raise ValueError('Ambiguous administrator audit history; promotion refused.')
    proposed = intents[0] if intents else {
        'id': uuid4().hex, 'user_id': user['id'], 'previous_role': 'client',
        'new_role': 'admin', 'method': 'OPERATOR_CLI', 'assigned_at': utc_now(),
        'protocol': 'AUDIT_BEFORE_ADMIN_CAS_V1', 'before_sha256': _fingerprint(user),
    }

    def validate(intent):
        if (not intent.get('id') or not intent.get('assigned_at')
                or intent.get('user_id') != user['id']
                or intent.get('previous_role') != 'client'
                or intent.get('new_role') != 'admin'
                or intent.get('method') != 'OPERATOR_CLI'):
            raise ValueError('Conflicting administrator audit intent; promotion refused.')
        if intent.get('protocol') == 'AUDIT_BEFORE_ADMIN_CAS_V1':
            if intent.get('before_sha256') != _fingerprint(user):
                raise ValueError('Stale administrator intent: account changed since authorization.')
        elif 'protocol' in intent or 'before_sha256' in intent:
            raise ValueError('Unknown administrator intent protocol.')
        elif any(user.get(k) is not None for k in
                 ('_revision', 'version', 'revision', 'updated_at', 'admin_role_intent_id',
                  'authority_capability_change_id')) or user.get('capabilities') or user.get('permissions'):
            # Old CLI intents lack a snapshot. Support only untouched legacy
            # client records; any evidence of subsequent mutation fails closed.
            raise ValueError('Legacy intent conflicts with account mutation metadata.')

    validate(proposed)
    intent = db.reserve_admin_role_intent(proposed)
    # Another process may have reserved or completed the same operation.
    latest = account()
    if latest.get('role') == 'admin' and latest.get('admin_role_intent_id') == intent['id']:
        return {'status': 'already_admin', 'user_id': user['id'], 'intent_id': intent['id']}
    validate(intent)

    def apply(current):
        if current.get('role') == 'admin' and current.get('admin_role_intent_id') == intent['id']:
            return {}
        if current != user or latest != user:
            raise ValueError('Account changed during promotion; intent retained, access unchanged.')
        return {'role': 'admin', 'admin_role_intent_id': intent['id']}

    db.mutate('users', user['id'], apply)
    return {'status': 'promoted', 'user_id': user['id'], 'intent_id': intent['id']}
