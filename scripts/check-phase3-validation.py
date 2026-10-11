"""Read-only checks of recorded real-provider validation, without another API call."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.models.understanding_outputs import VALIDATORS


def main():
    report = json.loads((ROOT / 'artifacts/phase3_core_validation.json').read_text(encoding='utf-8'))
    for language in ('english', 'tamil', 'hindi', 'telugu', 'mixed'):
        summary = report['cases'][language]
        assert all(summary['checks'].values()), (language, summary['checks'])
        detail = json.loads((ROOT / f'.localdev/phase3-live/{language}-details.json').read_text(encoding='utf-8'))
        data, raw = detail['board']['data'], detail['case']['raw_package']
        sources = {s['source_id']: s['original_text'] for s in raw['provenance']}
        for records in data.get('human', {}).values():
            for answer in records:
                if answer.get('response') == 'ANSWER':
                    sources[answer['source_id']] = answer['value']
        for path, validate in VALIDATORS.items():
            value = data
            for part in path.split('.'):
                value = value[part]
            validate(value)
        for collection in ('facts', 'incidents', 'timeline', 'parties'):
            for record in data[collection].values():
                for ref in record['source_refs']:
                    assert sources[ref['source_id']][ref['start']:ref['end']] == ref['wording'], (language, collection)
                    assert not ref['evidence_id'] or ref['evidence_id'] in raw['evidence_ids']
                if collection == 'parties' and record['name']:
                    assert any(record['name'] in ref['wording'] for ref in record['source_refs'])
        assert data['domain_classification']['primary_domain'] == 'CONSUMER'
        assert not data['domain_classification']['legal_corpus_ready']
        print(language + ': strict schemas, source offsets, identities and routing invariants PASS')
    router = json.loads((ROOT / 'artifacts/phase3_router_validation.json').read_text(encoding='utf-8'))
    assert len(router['results']) == 8 and all(case['passed'] for case in router['results'])
    print('Six domains, uncertain and injection router cases PASS')
    print('Language-equivalent consumer routing PASS; this does not assert identical fact counts or universal language support.')


if __name__ == '__main__':
    main()
