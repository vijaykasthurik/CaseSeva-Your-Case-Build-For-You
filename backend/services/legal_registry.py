from ..adapters.capabilities import llm_is_live
"""Production registrations generated from the selected team and stable issue IDs."""
from pydantic import TypeAdapter
from ..models.orchestration import AgentContract, AgentResult
from ..models.legal_foundation import SpecialistProposal, IssueCandidate
from ..models.legal_outputs import validate_issues, validate_team, Applications, Citations
from .understanding_agents import core_registry
from .specialist_packs import CATALOG, validate_descriptor
from .legal_team import LegalTeamAgents
from .legal_checks import LegalChecks
from .case_blackboard import digest
from .legal_artifacts import validate_specialist


def object_validator(required, optional=()):
    required, allowed = set(required), set(required) | set(optional)
    def validate(value):
        TypeAdapter(dict[str, object]).validate_python(value)
        if not required.issubset(value) or set(value) - allowed:
            raise ValueError('Legal output shape does not match declared contract')
        return value
    return validate


def issue_validator(value):
    return validate_issues(value)


def foundation_handler(issue_ids, optional, corpus):
    def run(claim):
        values, findings, gaps = claim['inputs'], {}, []
        for iid in issue_ids:
            apps = values['legal_applications.' + iid]
            citations = values['citation_verification.' + iid]
            verified = {d['source_id'] for d in citations['decisions'] if d['status'] == 'VERIFIED'}
            jurisdiction = values['jurisdiction_remedy.' + iid]
            evidence = values['evidence_law.' + iid]
            limitation = values.get('limitation.' + iid)
            temporal = values['temporal_findings.' + iid]['decisions']
            laws = [corpus.get(app['source_id'], app['source_version']) for app in apps['applications']]
            temporal_ready = bool(laws) and any(s and s['source_type'] != 'JUDGMENT' for s in laws) and all(
                s and (s['source_type'] == 'JUDGMENT' or temporal.get(s['source_id'], {}).get('status') == 'APPLICABLE') for s in laws)
            ready = (bool(apps['applications']) and not apps['unknowns'] and jurisdiction['status'] == 'SOURCE_VERIFIED'
                     and temporal_ready and not evidence['missing_elements'] and (not optional[iid]['limitation'] or limitation['status'] == 'SOURCE_VERIFIED'))
            authorities = sorted({app['source_id'] for app in apps['applications']})
            if not set(authorities).issubset(verified):
                raise ValueError('Established findings require verified citation coverage')
            findings[iid] = {'legal_issue_id': iid, 'status': 'SOURCE_VERIFIED' if ready else 'REVIEW_REQUIRED',
                'verified_source_ids': authorities, 'fact_ids': values['legal_issues.' + iid]['fact_ids'],
                'evidence_ids': values['legal_issues.' + iid]['evidence_ids'],
                'law_excerpts': [app['quote'] for app in apps['applications']],
                'interpretation_state': 'ADVOCATE_REVIEW_REQUIRED'}
            if not ready:
                gaps.append(iid)
        extra = values.get('legal_issue_scope', {}).get('further_issues_require_review')
        output = {'status': 'SOURCE_VERIFIED' if findings and not gaps and not extra else 'REVIEW_REQUIRED',
                  'findings': findings, 'unresolved_issue_ids': gaps, 'further_issues_require_review': bool(extra),
                  'understanding_reference': values.get('understanding_reference'),
                  'team_reference': {'path': 'agent_team', 'execution_id': values['agent_team']['execution_id']},
                  'execution_id': claim['execution_id'], 'review_state': 'ADVOCATE_REVIEW_REQUIRED'}
        return AgentResult(status='COMPLETED', outputs={'legal_foundation': output})
    return run


def legal_registry(adapters, corpus, board=None):
    registry = core_registry(adapters)
    team, checks = LegalTeamAgents(adapters), LegalChecks(adapters, corpus)
    reasoning_available = adapters is not None and (llm_is_live(adapters) or getattr(adapters, 'phase4_test_double', False))
    def register(name, handler, reads, writes, deps, validators, *, model=False, pack=None, granular=()):
        registry.register(AgentContract(agent_type=name, version='1.0.0', engine=1,
            purpose='Verified legal foundation capability: ' + name, reads=tuple(reads), writes=tuple(writes), dependencies=tuple(deps),
            required_inputs=tuple(reads), optional_inputs=(), pack=pack, can_run_concurrently=True, timeout_seconds=240,
            max_retries=1, required_capabilities=('legal_reasoning',) if model else (), visibility='ADVOCATE_INTERNAL'),
            handler, validators, available=reasoning_available if model else True, granular_writes=granular)
    base = ['case_issues', 'facts', 'parties', 'relationships', 'evidence_mapping', 'case_understanding.stage', 'domain_classification', 'input.evidence_ids']
    register('TEAM_BUILDER', team.team, base + ['legal_capabilities'], ['agent_team'], ['DOMAIN_ROUTER'],
             {'agent_team': validate_team}, model=True)
    # Every specialist is genuinely registered. Only selected names enter a plan.
    for name in CATALOG:
        path = 'specialists.' + name
        register(name, team.specialist(name), base + ['agent_team'], [path], ['TEAM_BUILDER'], {path: validate_specialist}, model=True, pack=CATALOG[name]['domain'])
    data = (board or {}).get('data', {})
    selections = data.get('agent_team', {}).get('selected', {})
    for name, value in selections.items():
        value = validate_descriptor(name, value)
        if value['issue_key'] is not None:
            path = 'specialists.' + name
            register(name, team.specialist(name), base + ['agent_team'], [path], ['TEAM_BUILDER'],
                     {path: validate_specialist}, model=True)
    selected = sorted(selections)
    if not selected:
        return registry, {'team': 'TEAM_BUILDER'}
    signature = digest(selected)[:10].upper()
    planner = 'LEGAL_ISSUES_' + signature
    register(planner, team.issues, base + ['agent_team'] + ['specialists.' + name for name in selected],
        ['legal_issues', 'legal_issue_scope'], selected, {'legal_issues': issue_validator, 'legal_issue_scope': object_validator(['further_issues_require_review'])}, model=True, granular=('legal_issues',))
    issue_ids = sorted(key for key, value in data.get('legal_issues', {}).items() if not value.get('superseded'))
    targets, optional = [], {}
    final_reads = ['agent_team', 'understanding_reference', 'legal_issue_scope']
    for iid in issue_ids:
        issue = data['legal_issues'][iid]
        optional[iid] = {'limitation': issue['limitation_relevant'], 'precedent': issue['precedent_useful']}
        # Contracts include issue-specific inputs and optional branches. A changed
        # shape gets a new identity; prior outputs remain in the audit history.
        fact_ids = sorted(set(issue['fact_ids'] + issue['contradicting_fact_ids'] + issue['date_fact_ids']))
        fact_reads = ['facts.' + fid for fid in fact_ids]
        suffix = '_' + iid + '_' + digest([signature, optional[iid], fact_ids])[:10].upper()
        def operation(prefix, handler, reads, path, dependencies, keys, model=False):
            name = prefix + suffix
            validator = checks.validate_applications if prefix == 'LEGAL_APPLICATION' else Citations.model_validate if prefix == 'CITATION_VERIFICATION' else object_validator(keys)
            register(name, handler, reads, [path], dependencies, {path: validator}, model=model)
            return name
        ref = 'legal_issues.' + iid
        source_path = 'legal_sources.candidates.' + iid
        statutes = operation('STATUTE_RETRIEVAL', checks.retrieval(iid), [ref, 'corpus_inputs.' + iid], source_path, [planner], ['issue_id', 'status', 'query', 'domain', 'jurisdiction', 'candidates', 'reason'])
        temporal = operation('TEMPORAL_LAW', checks.temporal(iid), [ref, *fact_reads, source_path], 'temporal_findings.' + iid, [statutes], ['issue_id', 'decisions'])
        citation_deps = [temporal]
        citation_reads = [ref, source_path, 'temporal_findings.' + iid]
        if issue['precedent_useful']:
            precedent = operation('PRECEDENT_RETRIEVAL', checks.retrieval(iid, True), [ref, 'corpus_inputs.' + iid], 'precedent_candidates.' + iid, [planner], ['issue_id', 'status', 'query', 'domain', 'jurisdiction', 'candidates', 'reason'])
            citation_deps.append(precedent)
            citation_reads.append('precedent_candidates.' + iid)
        citation = operation('CITATION_VERIFICATION', checks.citation(iid, issue['precedent_useful']), citation_reads, 'citation_verification.' + iid, citation_deps, ['issue_id', 'decisions'])
        application = operation('LEGAL_APPLICATION', checks.application(iid), [ref, *fact_reads, 'citation_verification.' + iid], 'legal_applications.' + iid, [citation], ['issue_id', 'status', 'applications', 'unknowns'], model=True)
        jurisdiction = operation('JURISDICTION_REMEDY', checks.jurisdiction(iid), [ref, 'legal_applications.' + iid, 'legal_context'], 'jurisdiction_remedy.' + iid, [application], ['issue_id', 'status', 'forums', 'remedies', 'unresolved'])
        evidence = operation('EVIDENCE_LAW', checks.evidence(iid), [ref, 'legal_applications.' + iid, 'evidence_mapping'], 'evidence_law.' + iid, [application], ['issue_id', 'elements', 'declared_not_uploaded', 'unavailable', 'unknown', 'missing_elements', 'review_required'])
        targets += [jurisdiction, evidence]
        final_reads += [ref, 'legal_applications.' + iid, 'citation_verification.' + iid, 'temporal_findings.' + iid, 'jurisdiction_remedy.' + iid, 'evidence_law.' + iid]
        if issue['limitation_relevant']:
            limit = operation('LIMITATION', checks.limitation(iid), [ref, *fact_reads, 'legal_applications.' + iid, 'limitation_triggers.' + iid], 'limitation.' + iid, [application], ['issue_id', 'status', 'deadline', 'trigger_date', 'source_id', 'reason', 'conditional'])
            targets.append(limit)
            final_reads.append('limitation.' + iid)
    if issue_ids:
        foundation = 'LEGAL_FOUNDATION_' + digest(['temporal-gate-v2', signature, targets])[:10].upper()
        register(foundation, foundation_handler(issue_ids, optional, corpus), final_reads, ['legal_foundation'], targets,
                 {'legal_foundation': object_validator(['status', 'findings', 'unresolved_issue_ids', 'further_issues_require_review', 'understanding_reference', 'team_reference', 'execution_id', 'review_state'])})
    else:
        foundation = None
    return registry, {'team': 'TEAM_BUILDER', 'specialists': selected, 'issues': planner, 'foundation': foundation}
