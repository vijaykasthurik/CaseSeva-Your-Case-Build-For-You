"""Prepare real downloaded sources for human review; NEVER approve authority.

Reads the existing local ingestion database. No network, credentials, model
calls, case edits or production writes. Sections and dates remain candidates.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.adapters.mock.database import MockDatabaseAdapter
from backend.services.verified_corpus import VerifiedCorpus
from backend.services.authority_review import AuthorityReview
from backend.models.case import utc_now


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', type=Path, default=ROOT / '.localdev/phase4-authority-review/database.json')
    args = parser.parse_args()
    if not args.database.is_file():
        raise SystemExit('Run official ingestion first; no source text is synthesized')
    db = MockDatabaseAdapter(args.database)
    corpus = VerifiedCorpus(db)
    review = AuthorityReview(corpus)
    downloads = [r for r in db.list('legal_ingestion_requests') if r['state'] == 'PARSED']
    records, notes = [], {}

    def document(fragment):
        matches = [r for r in downloads if fragment in r['official_url']]
        if not matches:
            raise ValueError('Missing official download: ' + fragment)
        return matches[-1]

    def add(download, sid, title, section, start, end, *, domain='CONSUMER', kind='STATUTE',
            effective=None, supports=(), rules=None, note=''):
        text = download['official_text']
        value = {k: download[k] for k in ('registry_id', 'official_url', 'final_url', 'retrieved_at',
                                           'raw_hash', 'content_hash', 'official_text')}
        value.update(source_id=sid, family=download['registry_id'], source_type=kind, domain=domain,
            jurisdiction='IN', title=title, section=section, citation=title + (', section ' + section if section else ''),
            source_language='en', quote=text[start:end], section_start=start, section_end=end,
            ingestion_id=download['id'], effective_from=effective, temporal_source_ids=list(supports),
            temporal_reviewed=False, rules=rules or {}, rules_reviewed=False,
            version_note='UNREVIEWED acceptance candidate. ' + note, corpus_version='phase4-review-candidate-1')
        current = corpus.get(sid)
        if current and current['review_state'] == 'REVIEWED_PRIMARY':
            raise ValueError('Refusing to overwrite a reviewed source; prepare an explicit revision')
        record = review.submit(value, actor='phase4-official-ingestion-script')
        records.append(record)
        notes[sid] = note

    act = document('CP%20Act%202019_')
    title = 'THE CONSUMER PROTECTION ACT, 2019'
    text = act['official_text']
    base = re.search(r'(?m)^2\. ', text).start()
    for child in (7, 10, 11):
        start = text.index('(' + str(child) + ')', base)
        end = text.index('(' + str(child + 1) + ')', start)
        add(act, 'cpa2019_s2_' + str(child), title, '2(' + str(child) + ')', start, end,
            effective='2020-07-20', supports=['cpa_commencement_2351'],
            note='Definition excerpt only; review exclusions, extraction and later amendments. Date candidate comes from S.O. 2351(E).')
    for section, next_section in ((34, 35), (39, 40), (69, 70)):
        start = re.search(r'(?m)^' + str(section) + r'\. ', text).start()
        end = start + re.search(r'(?m)^' + str(next_section) + r'\. ', text[start:]).start()
        quote = text[start:end]
        rules = {}
        if section == 39:
            rules = {'remedies': [{'quote': quote, 'requires': ['consumer_status', 'defect_or_deficiency', 'relief_basis']}]}
        if section == 69:
            rules = {'limitation': {'quote': quote, 'years': 2}}
        add(act, 'cpa2019_s' + str(section), title, str(section), start, end,
            effective='2020-07-20', supports=['cpa_commencement_2351'], rules=rules,
            note='Original 2019 text, not a current consolidated version. Section 34 pecuniary amount MUST be read with 2021 rules; limitation trigger and exclusions need case-specific review.')
    commencement = document('Act%20into%20force_')
    text = commencement['official_text']
    start = text.index('MINISTRY OF CONSUMER AFFAIRS')
    add(commencement, 'cpa_commencement_2351', 'MINISTRY OF CONSUMER AFFAIRS, FOOD AND PUBLIC DISTRIBUTION', None,
        start, len(text), kind='NOTIFICATION', effective='2020-07-20', supports=['cpa_commencement_2351'],
        note='S.O. 2351(E), 15 July 2020; 20 July 2020 commencement applies only to listed provisions and exclusions. This is the notification hosted by its issuing department, not live eGazette connectivity.')
    jurisdiction = document('232278_')
    text = jurisdiction['official_text']
    english = text.index('MINISTRY OF CONSUMER AFFAIRS')
    title = 'Consumer Protection (Jurisdiction of the District Commission, the State Commission and the National Commission) Rules, 2021'
    for section, next_section in ((1, 2), (3, 4)):
        start = english + re.search(r'(?m)^' + str(section) + r'\.\s', text[english:]).start()
        end = start + re.search(r'(?m)^' + str(next_section) + r'\.\s', text[start:]).start()
        rules = {'forums': [{'quote': text[start:end], 'requires': ['consideration_paid', 'territorial_basis', 'consumer_status']}]} if section == 3 else {}
        add(jurisdiction, 'cpa_jurisdiction2021_r' + str(section), title, str(section), start, end,
            kind='RULE', supports=['cpa_jurisdiction2021_r1'], rules=rules,
            note='G.S.R. 912(E). Verify publication/effective date: notification and Gazette header say 30 December 2021; upload/signature identifier says 31 December. Effective date intentionally unresolved pending review.')
    rti = document('RTI_English.pdf')
    text = rti['official_text']
    body = text.index('1. Short title, extent and commencement.', text.index('[15th June, 2005.]'))
    for section, next_section in ((1, 2), (3, 4), (6, 7), (7, 8), (19, 20)):
        start = body + re.search(r'(?m)^\s*' + str(section) + r'\.\s', text[body:]).start()
        end = start + re.search(r'(?m)^\s*' + str(next_section) + r'\.\s', text[start:]).start()
        add(rti, 'rti2005_s' + str(section), 'THE RIGHT TO INFORMATION ACT, 2005', str(section), start, end,
            domain='RTI_ADMINISTRATIVE', supports=['rti2005_s1'],
            note='Official compilation as on 18 November 2025. Section 1(3) distinguishes immediate and 120th-day commencement; exact applicable date and amendment history require review. Existing RTI fixture has no application date: no statutory deadline may be inferred.')

    folder = args.database.parent
    (folder / 'review-records.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    manifest = {'prepared_at': utc_now(), 'review_state': 'REVIEW_PENDING', 'reviewer': None,
        'database': str(args.database.resolve()), 'source_verified_count': 0,
        'records': [{k: r[k] for k in ('source_id', 'domain', 'official_url', 'final_url', 'retrieved_at', 'content_hash', 'raw_hash',
            'section', 'version_id', 'review_state', 'effective_from', 'temporal_reviewed', 'rules_reviewed')} | {'review_note': notes[r['source_id']]} for r in records],
        'failed_requests': [{k: r.get(k) for k in ('id', 'official_url', 'failure', 'retryable')} for r in db.list('legal_ingestion_requests') if r.get('failure')]}
    (ROOT / 'artifacts/phase4_authority_review_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# Phase 4 official authority review bundle', '', 'REVIEW_PENDING — none of these records establishes law.', '',
        'Original text, exact offsets, hashes and server-recorded retrieval times are in review-records.json and the local ingestion database.', '',
        'Review the original linked PDF, section identity and excerpt, later amendments, effective interval, temporal support and any structured rule. Do not approve a candidate with unresolved date/rule metadata. Identity checks are automated, not legal review.', '',
        'The authenticated admin review API is `/api/admin/authorities/{source_id}/review`. Supply the current expected_version, decision and rationale; reviewer identity/time are server-owned. Source edits are submitted as a new revision first. The submitter cannot approve their own revision. No admin account has been created or promoted for this bundle.', '']
    for record in records:
        lines += ['## ' + record['source_id'], '', record['citation'], '', record['official_url'], '',
            'Revision: `' + record['version_id'] + '`', '', notes[record['source_id']], '',
            'Exact extracted excerpt (unreviewed; compare PDF typography):', '', '```text', record['quote'], '```', '']
    (folder / 'REVIEW.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({'records': len(records), 'state': 'REVIEW_PENDING', 'bundle': str(folder / 'REVIEW.md')}))


if __name__ == '__main__':
    main()
