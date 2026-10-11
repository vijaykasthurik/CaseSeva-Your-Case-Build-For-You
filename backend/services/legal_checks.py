"""Deterministic authority gates and per-issue legal analysis handlers."""
from datetime import date
from dateutil.relativedelta import relativedelta
from ..models.orchestration import AgentResult
from ..models.legal_foundation import ApplicationProposal
from .legal_team import generate
from .understanding_agents import known_ids


def compact(source):
    return {key: source.get(key) for key in ('source_id', 'version_id', 'title', 'section', 'citation', 'court', 'source_type', 'jurisdiction',
        'quote', 'official_url', 'source_language', 'content_hash', 'retrieved_at', 'effective_from', 'effective_until', 'corpus_version')}


def issue_facts(values):
    return {path.removeprefix('facts.'): value for path, value in values.items() if path.startswith('facts.')}


class LegalChecks:
    def __init__(self, adapters, corpus):
        self.adapters, self.corpus = adapters, corpus

    def retrieval(self, issue_id, judgments=False):
        path = ('precedent_candidates.' if judgments else 'legal_sources.candidates.') + issue_id
        def run(claim):
            issue = claim['inputs']['legal_issues.' + issue_id]
            candidates = self.corpus.search(issue['domain'], issue['jurisdiction'], issue['query'], kind='JUDGMENT' if judgments else 'STATUTE')
            if judgments:
                candidates.sort(key=lambda s: s.get('rules', {}).get('authority_rank', 999))
            output = {'issue_id': issue_id, 'status': 'CANDIDATES' if candidates else 'LEGAL_SOURCE_PENDING',
                      'query': issue['query'], 'domain': issue['domain'], 'jurisdiction': issue['jurisdiction'],
                      'candidates': [{k: v for k, v in compact(s).items() if k != 'quote'} for s in candidates], 'reason': None if candidates else 'NO_MATCHING_SOURCE_COVERAGE'}
            return AgentResult(status='COMPLETED', outputs={path: output})
        return run

    def temporal(self, issue_id):
        def run(claim):
            values = claim['inputs']
            issue = values['legal_issues.' + issue_id]
            facts = issue_facts(values)
            dates = [facts[f]['date'].get('normalized') for f in issue['date_fact_ids']]
            exact = bool(dates) and all(dates) and all(facts[f]['date']['precision'] == 'EXACT_DATE' and facts[f]['certainty'] != 'CONFLICTED' for f in issue['date_fact_ids'])
            decisions = {}
            for candidate in values['legal_sources.candidates.' + issue_id]['candidates']:
                source = self.corpus.get(candidate['source_id'], candidate['version_id'])
                status, reason = 'PENDING', 'EVENT_DATE_OR_LEGAL_VERSION_UNRESOLVED'
                if exact and source and source['temporal_reviewed'] and source['effective_from'] and source['temporal_source_ids']:
                    supports = [self.corpus.get(sid) for sid in source['temporal_source_ids']]
                    support_ok = all(s and self.corpus.validate_source({k: v for k, v in s.items() if k != 'version_id'})[0] for s in supports)
                    if support_ok:
                        matches = [d >= source['effective_from'] and (not source['effective_until'] or d < source['effective_until']) for d in dates]
                        status = 'APPLICABLE' if all(matches) else 'NOT_APPLICABLE' if not any(matches) else 'CONFLICT'
                        reason = 'REVIEWED_EFFECTIVE_INTERVAL'
                decisions[candidate['source_id']] = {'status': status, 'reason': reason, 'version_id': candidate['version_id'],
                    'event_dates': dates, 'effective_from': source.get('effective_from') if source else None, 'effective_until': source.get('effective_until') if source else None}
            return AgentResult(status='COMPLETED', outputs={'temporal_findings.' + issue_id: {'issue_id': issue_id, 'decisions': decisions}})
        return run

    def citation(self, issue_id, with_precedents=False):
        def run(claim):
            values = claim['inputs']
            issue = values['legal_issues.' + issue_id]
            candidates = list(values['legal_sources.candidates.' + issue_id]['candidates'])
            if with_precedents:
                candidates += values['precedent_candidates.' + issue_id]['candidates']
            temporal = values['temporal_findings.' + issue_id]['decisions']
            decisions = []
            for candidate in candidates:
                source = self.corpus.get(candidate['source_id'], candidate['version_id'])
                state, reason = 'REJECTED', 'SOURCE_IDENTITY_MISMATCH'
                if source and all(candidate.get(k) == source.get(k) for k in ('title', 'section', 'citation', 'court', 'content_hash', 'official_url')) and ('quote' not in candidate or candidate['quote'] == source['quote']):
                    valid, reason = self.corpus.validate_source({k: v for k, v in source.items() if k != 'version_id'})
                    state = 'VERIFIED' if valid else 'PENDING'
                    current = self.corpus.get(source['source_id'])
                    if current['version_id'] != source['version_id']:
                        state, reason = 'OUTDATED', 'SOURCE_VERSION_CHANGED'
                    elif source['domain'] != issue['domain'] or source['jurisdiction'] not in {'IN', issue['jurisdiction']}:
                        state, reason = 'NOT_APPLICABLE', 'WRONG_DOMAIN_OR_JURISDICTION'
                    elif source['source_type'] != 'JUDGMENT':
                        applicability = temporal.get(source['source_id'], {}).get('status')
                        if applicability != 'APPLICABLE':
                            state, reason = ('NOT_APPLICABLE' if applicability == 'NOT_APPLICABLE' else 'PENDING'), 'TEMPORAL_APPLICABILITY_PENDING'
                decisions.append({'source_id': candidate['source_id'], 'version_id': candidate['version_id'], 'status': state, 'reason': reason})
            return AgentResult(status='COMPLETED', outputs={'citation_verification.' + issue_id: {'issue_id': issue_id, 'decisions': decisions}})
        return run

    def application(self, issue_id):
        def run(claim):
            values = claim['inputs']
            verified = {d['source_id']: self.corpus.get(d['source_id'], d['version_id']) for d in values['citation_verification.' + issue_id]['decisions'] if d['status'] == 'VERIFIED'}
            if not verified:
                output = {'issue_id': issue_id, 'status': 'PENDING_SOURCE', 'applications': [], 'unknowns': ['VERIFIED_APPLICABLE_AUTHORITY_REQUIRED']}
            else:
                result = generate(self.adapters, 'APPLICATION_' + issue_id, ApplicationProposal, {**values, 'verified_sources': [compact(s) for s in verified.values()]},
                    'Map this legal issue to the supplied verified sources only. Copy title/citation/section and exact supporting quote. '
                    'Explain relevance as conditional and advocate-reviewable, never a guaranteed outcome. Required elements must be exact excerpts of supplied law. '
                    'For each element, map only the specific supporting and contradicting Fact IDs; record unknowns and leave unsupported elements without facts. '
                    'Keep contradictory/adverse authority; do not invent legal tests. Do not use merely similar authority if issue applicability is uncertain.')
                applications = []
                issue = values['legal_issues.' + issue_id]
                for item in result.applications:
                    source = verified.get(item.source_id)
                    known_ids(item.fact_ids, issue['fact_ids'] + issue['contradicting_fact_ids'])
                    if not source or any(getattr(item, k) != source[k] for k in ('title', 'section', 'citation')) or item.quote not in source['quote']:
                        raise ValueError('Unverified legal proposition/citation')
                    if any(element not in source['quote'] for element in item.required_elements):
                        raise ValueError('Legal ingredient absent from authoritative excerpt')
                    if len({m.element for m in item.element_mapping}) != len(item.element_mapping):
                        raise ValueError('Duplicate legal ingredient mapping')
                    for mapping in item.element_mapping:
                        if mapping.element not in item.required_elements:
                            raise ValueError('Mapped ingredient is not declared')
                        known_ids(mapping.fact_ids + mapping.contradicting_fact_ids, item.fact_ids)
                    applications.append({**item.model_dump(), 'source_version': source['version_id'], 'authority_state': 'SOURCE_VERIFIED',
                                         'applicability_state': 'ADVOCATE_REVIEW_REQUIRED'})
                output = {'issue_id': issue_id, 'status': 'SOURCE_VERIFIED' if applications else 'REVIEW_REQUIRED', 'applications': applications, 'unknowns': result.unknowns}
            return AgentResult(status='COMPLETED', outputs={'legal_applications.' + issue_id: output})
        return run

    def jurisdiction(self, issue_id):
        def run(claim):
            values = claim['inputs']
            issue = values['legal_issues.' + issue_id]
            forums, remedies, gaps = [], [], []
            for application in values['legal_applications.' + issue_id]['applications']:
                source = self.corpus.get(application['source_id'], application['source_version'])
                rules = source.get('rules', {}) if source.get('rules_reviewed') else {}
                for kind, target in [('forums', forums), ('remedies', remedies)]:
                    for rule in rules.get(kind, []):
                        if not rule.get('quote') or rule['quote'] not in source['quote']:
                            raise ValueError('Reviewed legal rule lacks source support')
                        context = values.get('legal_context', {})
                        # A supplied amount/location is not a reviewed jurisdiction
                        # conclusion. Conditional rules require an explicit reviewed
                        # applicability decision, bound to this source version.
                        reviewed = context.get(source['source_id'], {})
                        missing = [key for key in rule.get('requires', []) if key not in reviewed.get('facts', {})]
                        if rule.get('requires') and (not reviewed.get('reviewed_by') or reviewed.get('source_version') != source['version_id'] or reviewed.get('applicable') is not True):
                            missing.append('RULE_APPLICABILITY_REQUIRES_REVIEW')
                        if not issue['jurisdiction'] or not issue['jurisdiction_fact_ids'] or missing:
                            gaps.extend(missing or ['JURISDICTION_UNKNOWN'])
                            continue
                        target.append({'description': rule['quote'], 'source_id': source['source_id'], 'source_version': source['version_id'],
                            'basis_fact_ids': issue['jurisdiction_fact_ids'], 'status': 'SOURCE_VERIFIED', 'conditional': True})
            if not forums:
                gaps.append('FORUM_BASIS_REQUIRES_REVIEW')
            if not remedies:
                gaps.append('REMEDY_BASIS_REQUIRES_REVIEW')
            return AgentResult(status='COMPLETED', outputs={'jurisdiction_remedy.' + issue_id: {'issue_id': issue_id,
                'status': 'REVIEW_REQUIRED' if gaps else 'SOURCE_VERIFIED', 'forums': forums, 'remedies': remedies, 'unresolved': sorted(set(gaps))}})
        return run

    def limitation(self, issue_id):
        def run(claim):
            values = claim['inputs']
            decision = values.get('limitation_triggers.' + issue_id) or {}
            output = {'issue_id': issue_id, 'status': 'REVIEW_REQUIRED', 'deadline': None, 'trigger_date': None,
                      'source_id': None, 'reason': 'TRIGGER_RULE_AND_EXCLUSIONS_REQUIRE_REVIEW', 'conditional': True}
            computed = []
            for app in values['legal_applications.' + issue_id]['applications']:
                source = self.corpus.get(app['source_id'], app['source_version'])
                rule = source.get('rules', {}).get('limitation') if source.get('rules_reviewed') else None
                if not rule or not decision.get('reviewed_by') or decision.get('source_id') != source['source_id'] or decision.get('source_version') != source['version_id']:
                    continue
                if not rule.get('quote') or rule['quote'] not in source['quote']:
                    raise ValueError('Limitation rule lacks authoritative support')
                if decision.get('fact_id') not in values['legal_issues.' + issue_id]['date_fact_ids']:
                    continue
                fact = issue_facts(values).get(decision.get('fact_id'), {})
                if not fact or fact['certainty'] == 'CONFLICTED' or fact['date']['precision'] != 'EXACT_DATE' or not fact['date'].get('normalized') or not decision.get('exclusions_reviewed'):
                    continue
                delta = {key: rule.get(key, 0) for key in ('years', 'months', 'days')}
                if not all(type(n) is int and n >= 0 for n in delta.values()) or not any(delta.values()):
                    raise ValueError('Invalid reviewed limitation interval')
                trigger = date.fromisoformat(fact['date']['normalized'])
                computed.append({'trigger_date': trigger.isoformat(), 'deadline': (trigger + relativedelta(**delta)).isoformat(), 'source_id': source['source_id']})
            if computed and all(c == computed[0] for c in computed):
                output.update(computed[0], status='SOURCE_VERIFIED', reason='REVIEWED_TRIGGER_RULE_AND_EXCLUSIONS')
            elif computed:
                output['reason'] = 'CONFLICTING_LIMITATION_RULES_REQUIRE_REVIEW'
            return AgentResult(status='COMPLETED', outputs={'limitation.' + issue_id: output})
        return run

    def evidence(self, issue_id):
        def run(claim):
            values = claim['inputs']
            issue = values['legal_issues.' + issue_id]
            mapping = values['evidence_mapping']
            elements = []
            missing = False
            for app in values['legal_applications.' + issue_id]['applications']:
                specific = {m['element']: m for m in app['element_mapping']}
                for element in app['required_elements']:
                    link = specific.get(element, {})
                    fact_ids = link.get('fact_ids', [])
                    missing = missing or not fact_ids or bool(link.get('unknowns'))
                    elements.append({'element': element, 'source_id': app['source_id'], 'fact_ids': fact_ids,
                        'contradicting_fact_ids': link.get('contradicting_fact_ids', []), 'unknowns': link.get('unknowns', []),
                        'fact_support': {fid: mapping.get('fact_support', {}).get(fid, {'state': 'UNKNOWN', 'evidence_ids': []}) for fid in fact_ids},
                        'element_satisfaction': 'ADVOCATE_REVIEW_REQUIRED'})
            return AgentResult(status='COMPLETED', outputs={'evidence_law.' + issue_id: {'issue_id': issue_id, 'elements': elements,
                'declared_not_uploaded': mapping.get('declared_evidence', []), 'unavailable': mapping.get('unavailable_evidence', []),
                'unknown': mapping.get('unknown_evidence', []), 'missing_elements': missing or not bool(elements), 'review_required': True}})
        return run
