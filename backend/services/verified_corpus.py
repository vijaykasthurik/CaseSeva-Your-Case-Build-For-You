"""Versioned extension of the existing LegalKnowledge verification boundary."""
import re
from datetime import date
from urllib.parse import urlparse
from ..models.legal_foundation import LegalSource
from .legal_knowledge import LegalKnowledge, source_record
from .case_blackboard import digest, CaseBlackboard


class VerifiedCorpus:
    def __init__(self, db, knowledge=None):
        self.db, self.knowledge = db, knowledge or LegalKnowledge()

    def validate_source(self, record):
        value = LegalSource.model_validate(record).model_dump()
        from .authority_review import authority_digest
        receipt = self.db.get('legal_authority_reviews', value.get('review_id') or '')
        if (value['review_state'] != 'REVIEWED_PRIMARY' or value['revision_status'] == 'REVISION_REQUESTED' or not value['source_reviewed'] or not receipt
            or receipt.get('decision') != 'REVIEWED_PRIMARY' or receipt.get('source_id') != value['source_id']
            or receipt.get('source_digest') != authority_digest(value)
            or receipt.get('reviewer_id') != value['reviewed_by'] or receipt.get('reviewed_at') != value['reviewed_at']):
            return False, 'Independent primary authority review required'
        return self.validate_identity(value)

    def validate_identity(self, record):
        """Checks source identity only; this method cannot establish verified law.

        A record-specific admin approval replaces global source enablement for
        this corpus. It does not enable legacy summaries or nationwide coverage.
        """
        value = LegalSource.model_validate(record).model_dump()
        registry = {k: {**v, 'enabled': True} for k, v in self.knowledge.sources.items()}
        valid, reason = source_record({**value, 'source_id': value['registry_id'], 'source_url': value['official_url'],
            'source_reviewed': True, 'reviewed_by': 'identity-check-only'}, registry)
        if not valid:
            return False, reason
        for address in (value['official_url'], value['final_url']):
            parsed = urlparse(address or '')
            if (parsed.scheme != 'https' or parsed.hostname not in registry[value['registry_id']]['hosts']
                or parsed.username or parsed.password or parsed.port not in (None, 443)):
                return False, 'Official canonical and final URLs must match registered hosts'
        if value['official_text'][value['section_start']:value['section_end']] != value['quote']:
            return False, 'Reviewed section boundary does not match original text'
        compact = lambda s: ' '.join(s.split()).casefold()
        if compact(value['title']) not in compact(value['official_text']):
            return False, 'Title absent from authoritative text'
        if value['source_type'] == 'JUDGMENT':
            if not value['court'] or compact(value['citation']) not in compact(value['official_text']) or compact(value['court']) not in compact(value['official_text']):
                return False, 'Judgment citation/court absent from original'
        elif value['section']:
            subsection = re.fullmatch(r'(\d+)\((\d+)\)', value['section'])
            if subsection:
                parent, child = subsection.groups()
                starts = list(re.finditer(r'(?m)^\s*' + re.escape(parent) + r'\.\s', value['official_text']))
                preceding = [m for m in starts if m.start() < value['section_start']]
                following = re.search(r'(?m)^\s*' + str(int(parent) + 1) + r'\.\s', value['official_text'][preceding[-1].end():]) if preceding else None
                if (not preceding or not following or value['section_end'] > preceding[-1].end() + following.start()
                    or not value['quote'].lstrip().startswith('(' + child + ')')):
                    return False, 'Subsection is outside its identified parent section'
            elif not re.search(r'(?:^|\n)\s*' + re.escape(value['section']) + r'(?:[.\s(]|$)', value['quote']):
                return False, 'Section identifier absent from reviewed section boundary'
        for key in ('effective_from', 'effective_until'):
            if value[key]:
                date.fromisoformat(value[key])
        if value['effective_from'] and value['effective_until'] and value['effective_from'] >= value['effective_until']:
            return False, 'Invalid effective date interval'
        return True, 'Reviewed primary text, identity and section boundary match'

    def publish(self, record, *, expected_version=None, activate=True):
        """Trusted ingestion API only. No citizen/model route may invoke this."""
        value = LegalSource.model_validate(record).model_dump()
        valid, reason = self.validate_source(value)
        value['verification'] = 'VERIFIED' if valid else 'PENDING'
        version = digest(value)
        stored = {'id': version, 'source': value, 'reason': reason}
        if not self.db.get('legal_authority_versions', version):
            self.db.create('legal_authority_versions', stored)
        if not activate:
            return {**value, 'version_id': version, 'reason': reason}
        head = {'id': value['source_id'], 'version': version}
        if self.db.get('legal_authority_heads', value['source_id']):
            def advance(current):
                if expected_version is not None and current['version'] != expected_version:
                    raise ValueError('Authority changed during review')
                return head
            self.db.mutate('legal_authority_heads', value['source_id'], advance)
        else:
            self.db.create('legal_authority_heads', head)
        return {**value, 'version_id': version, 'reason': reason}

    def sources(self):
        return [{**self.db.get('legal_authority_versions', h['version'])['source'], 'version_id': h['version']}
                for h in self.db.list('legal_authority_heads')]

    def get(self, source_id, version_id=None):
        head = self.db.get('legal_authority_heads', source_id)
        if not head:
            return None
        record = self.db.get('legal_authority_versions', version_id or head['version'])
        if not record or record['source']['source_id'] != source_id:
            return None
        return {**record['source'], 'version_id': record['id']}

    def search(self, domain, jurisdiction, query, *, kind='STATUTE', limit=12):
        terms = set(re.findall(r'\w+', query.casefold()))
        candidates = []
        for source in self.sources():
            if source['domain'] != domain or not jurisdiction or source['jurisdiction'] not in {jurisdiction, 'IN'}:
                continue
            if (kind == 'JUDGMENT') != (source['source_type'] == 'JUDGMENT'):
                continue
            score = len(terms & set(re.findall(r'\w+', (source['title'] + ' ' + source['quote']).casefold())))
            if score:
                candidates.append((score, source))
        return [source for _, source in sorted(candidates, key=lambda x: (-x[0], x[1]['source_id']))[:limit]]

    def readiness(self):
        result = []
        for source in self.sources():
            valid, reason = self.validate_source({k: v for k, v in source.items() if k != 'version_id'})
            result.append({key: source[key] for key in ('source_id', 'domain', 'jurisdiction', 'family', 'source_type', 'court', 'effective_from', 'effective_until', 'corpus_version', 'version_id')}
                          | {'status': 'SOURCE_VERIFIED' if valid else 'PENDING', 'review_state': source['review_state'], 'revision_status': source.get('revision_status', 'NONE'), 'reason': reason})
        return result

    def sync_case(self, case_id):
        """Version fingerprints are field-scoped, so unrelated issues stay current."""
        store = CaseBlackboard(self.db)
        board = store.read_board(case_id)
        changes = {}
        for issue_id, issue in board['data'].get('legal_issues', {}).items():
            if issue.get('superseded'):
                continue
            candidates = self.search(issue['domain'], issue.get('jurisdiction'), issue['query'])
            if issue.get('precedent_useful'):
                candidates += self.search(issue['domain'], issue.get('jurisdiction'), issue['query'], kind='JUDGMENT')
            dependencies = {s['source_id']: s for s in candidates}
            for source in candidates:
                for sid in source['temporal_source_ids']:
                    support = self.get(sid)
                    if support:
                        dependencies[sid] = support
            # Freshness is a dependency as well as content: unchanged bytes can
            # become unusable when their review window expires.
            changes['corpus_inputs.' + issue_id] = digest(sorted((s['source_id'], s['version_id'],
                self.validate_source({k: v for k, v in s.items() if k != 'version_id'})[0]) for s in dependencies.values()))
        if changes:
            return store.append_change(case_id, changes, actor='source-registry', reason='Legal source versions synchronized')
        return board
