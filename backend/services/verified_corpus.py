"""Versioned extension of the existing LegalKnowledge verification boundary."""
import re
from datetime import date
from ..models.legal_foundation import LegalSource
from .legal_knowledge import LegalKnowledge, source_record
from .case_blackboard import digest, CaseBlackboard


class VerifiedCorpus:
    def __init__(self, db, knowledge=None):
        self.db, self.knowledge = db, knowledge or LegalKnowledge()

    def validate_source(self, record):
        value = LegalSource.model_validate(record).model_dump()
        valid, reason = source_record({**value, 'source_id': value['registry_id'], 'source_url': value['official_url']}, self.knowledge.sources)
        if not valid:
            return False, reason
        if value['official_text'][value['section_start']:value['section_end']] != value['quote']:
            return False, 'Reviewed section boundary does not match original text'
        compact = lambda s: ' '.join(s.split()).casefold()
        if compact(value['title']) not in compact(value['official_text']):
            return False, 'Title absent from authoritative text'
        if value['source_type'] == 'JUDGMENT':
            if not value['court'] or compact(value['citation']) not in compact(value['official_text']) or compact(value['court']) not in compact(value['official_text']):
                return False, 'Judgment citation/court absent from original'
        elif value['section'] and not re.search(r'(?:^|\n)\s*' + re.escape(value['section']) + r'(?:[.\s(]|$)', value['quote']):
            return False, 'Section identifier absent from reviewed section boundary'
        for key in ('effective_from', 'effective_until'):
            if value[key]:
                date.fromisoformat(value[key])
        if value['effective_from'] and value['effective_until'] and value['effective_from'] >= value['effective_until']:
            return False, 'Invalid effective date interval'
        return True, 'Reviewed primary text, identity and section boundary match'

    def publish(self, record):
        """Trusted ingestion API only. No citizen/model route may invoke this."""
        value = LegalSource.model_validate(record).model_dump()
        valid, reason = self.validate_source(value)
        value['verification'] = 'VERIFIED' if valid else 'PENDING'
        version = digest(value)
        stored = {'id': version, 'source': value, 'reason': reason}
        if not self.db.get('legal_authority_versions', version):
            self.db.create('legal_authority_versions', stored)
        head = {'id': value['source_id'], 'version': version}
        if self.db.get('legal_authority_heads', value['source_id']):
            self.db.update('legal_authority_heads', value['source_id'], head)
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
                          | {'status': 'SOURCE_VERIFIED' if valid else 'PENDING', 'reason': reason})
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
