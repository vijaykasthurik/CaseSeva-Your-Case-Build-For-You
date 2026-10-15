"""Eligibility only. Does not implement or dispatch a downstream engine."""
from .legal_visibility import current_case_file

ENGINE2_NOT_RUN_DISCLOSURE = 'Case Challenge / Argument Analysis was not run.'


def reviewed_engine1_current(case, db=None):
    file = current_case_file(case, db)
    if not file or not file.get('version'):
        return False
    if case.get('advocate_approved_case_file_version') != file['version']:
        return False
    if case.get('engines', {}).get('1', {}).get('status') in {'STALE', 'RUNNING', 'FAILED'}:
        return False
    if file.get('input_version', case.get('input_version', 1)) != case.get('input_version', 1):
        return False
    return not case.get('processing_error')
