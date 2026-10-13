"""Official ingestion and explicit, authenticated review of existing corpus records.

No download, parser, model or submitter can grant its own primary authority status.
The HTTP boundary authenticates the admin; this internal service additionally
checks the persisted account and binds decisions to immutable source content.
"""
from uuid import uuid4
from urllib.error import URLError, HTTPError
from ..models.case import utc_now
from ..models.legal_foundation import LegalSource
from ..adapters.real.official_sources import OfficialSourceAdapter
from .case_blackboard import digest

REVIEW_FIELDS = {'review_id', 'reviewed_at', 'reviewed_by', 'source_reviewed', 'review_state', 'verification', 'revision_status'}


def authority_digest(value):
    fields = {k: v for k, v in LegalSource.model_validate(value).model_dump().items() if k not in REVIEW_FIELDS}
    # Preserve existing receipt signatures when optional revision metadata is absent.
    for key in ('parent_revision', 'revision_request_id', 'revision_metadata'):
        if not fields.get(key):
            fields.pop(key, None)
    return digest(fields)


class AuthorityReview:
    def __init__(self, corpus, accounts_db=None):
        self.corpus, self.db = corpus, corpus.db
        self.accounts_db = accounts_db or self.db

    def ingest(self, registry_id, url, *, adapter=None):
        request_id = uuid4().hex
        self.db.create('legal_ingestion_requests', {'id': request_id, 'registry_id': registry_id,
            'official_url': url, 'state': 'DISCOVERED', 'created_at': utc_now(),
            'events': [{'state': 'DISCOVERED', 'at': utc_now()}]})
        def transition(state, **fields):
            self.db.mutate('legal_ingestion_requests', request_id, lambda old: {
                **fields, 'state': state, 'events': old['events'] + [{'state': state, 'at': utc_now()}]})
        try:
            result = (adapter or OfficialSourceAdapter(self.corpus.knowledge)).fetch(registry_id, url,
                on_download=lambda metadata: transition('DOWNLOADED', **metadata))
            transition('PARSED', **result)
        except (TimeoutError, URLError) as exc:
            retryable = not isinstance(exc, HTTPError) or exc.code in {408, 429, 500, 502, 503, 504}
            self.db.update('legal_ingestion_requests', request_id, {'failure': type(exc).__name__,
                'retryable': retryable, 'last_attempt_at': utc_now()})
        except (ValueError, UnicodeError) as exc:
            self.db.update('legal_ingestion_requests', request_id, {'failure': type(exc).__name__,
                'retryable': False, 'last_attempt_at': utc_now()})
        return self.db.get('legal_ingestion_requests', request_id)

    def submit(self, record, *, actor, activate=True):
        value = LegalSource.model_validate(record).model_dump()
        current = self.corpus.get(value['source_id'])
        download = self.db.get('legal_ingestion_requests', value.get('ingestion_id') or '')
        if not download or download['state'] != 'PARSED':
            raise ValueError('A parsed official ingestion record is required')
        for key in ('registry_id', 'official_url', 'final_url', 'retrieved_at', 'raw_hash', 'content_hash', 'official_text'):
            if value[key] != download.get(key):
                raise ValueError('Authority does not match its official download')
        # Identity checks are separate from approval and cannot enable law.
        valid, reason = self.corpus.validate_identity(value)
        if not valid:
            raise ValueError(reason)
        if current and current.get('revision_status') == 'REVISION_REQUESTED':
            ignored = REVIEW_FIELDS | {'parent_revision', 'revision_request_id'}
            prior = LegalSource.model_validate({k: v for k, v in current.items() if k != 'version_id'}).model_dump()
            if {k: v for k, v in value.items() if k not in ignored} == {k: v for k, v in prior.items() if k not in ignored}:
                raise ValueError('A revision request requires corrected content or metadata')
        value.update(parent_revision=current['version_id'] if current else None,
            revision_request_id=(current.get('review_id') if current and current.get('revision_status') == 'REVISION_REQUESTED' else None),
            revision_status='NONE')
        value.update(review_state='REVIEW_PENDING', review_id=None, reviewed_at=None,
                     reviewed_by=None, source_reviewed=False, verification='PENDING')
        pending = self.corpus.publish(value, activate=False)
        if not activate:
            return pending  # Preparation is not an authenticated submission.
        submission = self.db.get('legal_review_submissions', pending['version_id'])
        if submission and submission['actor'] != actor:
            raise ValueError('Revision already attributed to another submitter; prepare a new revision')
        if not submission:
            self.db.create('legal_review_submissions', {'id': pending['version_id'], 'actor': actor,
                'source_id': value['source_id'], 'submitted_at': utc_now(),
                'events': [{'state': 'IDENTITY_CHECKED', 'at': utc_now()}, {'state': 'REVIEW_PENDING', 'at': utc_now()}]})
        return self.corpus.publish(value, expected_version=current['version_id'] if current else None)

    def decide(self, source_id, expected_version, *, reviewer, decision, note):
        account = self.accounts_db.get('users', reviewer['id'])
        if not account or account.get('role') != 'admin' or reviewer.get('role') != 'admin':
            raise PermissionError('An authenticated administrator is required')
        if decision not in {'REVIEWED_PRIMARY', 'REJECTED', 'STALE', 'NEEDS_NEW_REVISION'} or not note.strip():
            raise ValueError('Explicit decision and review rationale required')
        source = self.corpus.get(source_id)
        if not source or source['version_id'] != expected_version:
            raise ValueError('Authority revision changed; review the current revision')
        submission = self.db.get('legal_review_submissions', expected_version)
        if decision == 'REVIEWED_PRIMARY':
            if source['review_state'] != 'REVIEW_PENDING' or source.get('revision_status') == 'REVISION_REQUESTED' or not submission:
                raise ValueError('Submit a new revision for independent review')
            if submission['actor'] == reviewer['id']:
                raise PermissionError('The submitter cannot independently approve this authority')
            valid, reason = self.corpus.validate_identity({k: v for k, v in source.items() if k != 'version_id'})
            if not valid:
                raise ValueError(reason)
        value = {k: v for k, v in source.items() if k != 'version_id'}
        review_id, now = uuid4().hex, utc_now()
        receipt = {'id': review_id, 'source_id': source_id, 'source_digest': authority_digest(value),
            'input_version': expected_version, 'reviewer_id': reviewer['id'], 'reviewed_at': now,
            'decision': decision, 'note': note}
        self.db.create('legal_authority_reviews', receipt)
        value.update(review_id=review_id, reviewed_by=reviewer['id'], reviewed_at=now,
                     review_state='REVIEW_PENDING' if decision == 'NEEDS_NEW_REVISION' else decision,
                     revision_status='REVISION_REQUESTED' if decision == 'NEEDS_NEW_REVISION' else value.get('revision_status', 'NONE'),
                     source_reviewed=decision == 'REVIEWED_PRIMARY')
        return self.corpus.publish(value, expected_version=expected_version)
