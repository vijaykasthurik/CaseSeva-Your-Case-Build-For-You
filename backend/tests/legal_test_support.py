"""Fictional authority and deterministic provider; never loaded by production."""
import copy
import hashlib
import json
from types import SimpleNamespace
from backend.models.case import utc_now
from backend.services.specialist_packs import PACKS
from backend.tests.core_test_support import CoreTestModel


class LegalTestModel(CoreTestModel):
    def generate(self, prompt, schema):
        if schema['stage'].startswith('core_'):
            return super().generate(prompt, schema)
        name = schema['stage'].removeprefix('foundation_').upper()
        self.calls.append(name)
        context = json.loads(prompt.split('CASE DATA:\n', 1)[1])
        agent = next(iter(PACKS[self.domain]))
        if name == 'TEAM_BUILDER':
            result = {'selected': [{'agent': agent, 'fact_ids': ['F001'], 'reason': 'Fixture fact'}],
                      'limitation_relevant': False, 'precedent_useful': False, 'optional_reason': 'Fixture scope'}
        elif name == 'LEGAL_ISSUES':
            result = {'issues': [{'key': 'purchase', 'statement': 'Fixture purchase question', 'category': 'PURCHASE',
                'domain': self.domain, 'fact_ids': ['F001'], 'date_fact_ids': ['F001'], 'specialist_origins': [agent],
                'query': 'refrigerator purchase', 'jurisdiction': 'IN', 'jurisdiction_fact_ids': ['F001'],
                'limitation_relevant': False, 'precedent_useful': False}]}
        elif name.startswith('APPLICATION_'):
            source = context['verified_sources'][0]
            result = {'applications': [{k: source[k] for k in ('source_id', 'citation', 'title', 'section', 'quote')} |
                {'fact_ids': ['F001'], 'explanation': 'Fictional fixture only, conditional relevance', 'required_elements': ['purchase'],
                 'element_mapping': [{'element': 'purchase', 'fact_ids': ['F001']}]}], 'unknowns': []}
        else:
            result = {'observations': [{'observation': 'Fixture question', 'fact_ids': ['F001']}], 'issue_families': ['purchase']}
        override = self.overrides.get(name)
        return override(copy.deepcopy(result), context) if callable(override) else copy.deepcopy({**result, **(override or {})})


def test_knowledge():
    return SimpleNamespace(sources={'fixture': {'tier': 'PRIMARY', 'enabled': True, 'hosts': ['example.test'], 'refresh_days': 30}})


def authority(**changes):
    quote = '1. A refrigerator purchase may be reviewed by Fixture Forum. A refund may be considered.'
    text = 'Fictional Test Act\n' + quote
    return {'source_id': 'fixture_act', 'family': 'fictional', 'source_type': 'STATUTE', 'domain': 'CONSUMER',
        'jurisdiction': 'IN', 'title': 'Fictional Test Act', 'section': '1', 'citation': 'Fictional Test Act, section 1',
        'official_url': 'https://example.test/fixture', 'final_url': 'https://example.test/fixture', 'registry_id': 'fixture', 'source_language': 'en',
        'official_text': text, 'quote': quote, 'content_hash': hashlib.sha256(text.encode()).hexdigest(),
        'retrieved_at': utc_now(), 'effective_from': '2020-01-01', 'temporal_source_ids': ['fixture_act'],
        'temporal_reviewed': True, 'version_note': 'TEST ONLY', 'corpus_version': 'fixture1',
        'source_reviewed': True, 'reviewed_by': 'TEST ONLY', 'section_start': text.index(quote), 'section_end': len(text),
        'rules_reviewed': True, 'rules': {'forums': [{'quote': 'Fixture Forum'}], 'remedies': [{'quote': 'refund'}]}, **changes}


def publish_reviewed(corpus, record):
    """Explicit fictional test review through the production gate, never live data."""
    from uuid import uuid4
    from backend.services.authority_review import AuthorityReview
    from backend.models.legal_foundation import LegalSource
    db = corpus.db
    user = {'id': 'test-independent-admin', 'role': 'admin'}
    if not db.get('users', user['id']):
        db.create('users', user)
    value = LegalSource.model_validate(record).model_dump()
    value['ingestion_id'] = uuid4().hex
    db.create('legal_ingestion_requests', {'id': value['ingestion_id'], 'state': 'PARSED',
        **{k: value[k] for k in ('registry_id', 'official_url', 'final_url', 'retrieved_at', 'raw_hash', 'content_hash', 'official_text')}})
    workflow = AuthorityReview(corpus)
    pending = workflow.submit(value, actor='test-fixture-ingestion')
    return workflow.decide(value['source_id'], pending['version_id'], reviewer=user,
                           decision='REVIEWED_PRIMARY', note='Fictional unit-test authority only')
