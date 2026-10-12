"""Revalidate published authority on every projection, including shared cases."""


def authority_manifest(corpus, source_ids):
    result, pending = {}, list(source_ids)
    while pending:
        source_id = pending.pop()
        if source_id in result:
            continue
        source = corpus.get(source_id)
        if not source or not corpus.validate_source({k: v for k, v in source.items() if k != 'version_id'})[0]:
            raise ValueError('Published authority is no longer reviewed and current')
        result[source_id] = source['version_id']
        if source['source_type'] != 'JUDGMENT':
            if not source['temporal_reviewed'] or not source['effective_from'] or not source['temporal_source_ids']:
                raise ValueError('Reviewed temporal support is required')
            pending.extend(source['temporal_source_ids'])
    if not result:
        raise ValueError('Empty authority coverage')
    return result


def current_case_file(case, db=None, *, corpus=None):
    file = case.get('case_file') or {}
    if file.get('kind') != 'SOURCE_VERIFIED_ENGINE1':
        return file
    if not case.get('legal_case_file_current') or file.get('input_version') != case.get('input_version', 1):
        return {}
    if corpus is None:
        if db is None:
            return {}  # No trust in cached flags when an authority check is unavailable.
        from .verified_corpus import VerifiedCorpus
        corpus = VerifiedCorpus(db)
    try:
        current = authority_manifest(corpus, [law['provision_id'] for law in file['applicable_law']])
        if current != file.get('authority_versions'):
            return {}
        if any(current.get(law['provision_id']) != law['source_version'] for law in file['applicable_law']):
            return {}
    except (ValueError, KeyError, TypeError):
        return {}
    return file
