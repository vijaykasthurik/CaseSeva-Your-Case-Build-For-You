"""Eligibility only. Does not implement or dispatch a downstream engine."""
from .legal_visibility import current_case_file

ENGINE2_NOT_RUN_DISCLOSURE = 'Case Challenge / Argument Analysis was not run.'


def reviewed_engine1_current(case, db=None):
    file = current_case_file(case, db)
    if not file or not file.get('version'):
        file = case.get('canonical_case_file') or case.get('case_file') or {}
        if not file or not file.get('version'):
            return False
    if case.get('advocate_approved_case_file_version') != file['version']:
        return False
    if case.get('engines', {}).get('1', {}).get('status') in {'STALE', 'RUNNING', 'FAILED'}:
        return False
    if case.get('engine1_stale'):
        return False
    if file.get('input_version', case.get('input_version', 1)) != case.get('input_version', 1):
        return False
    return not case.get('processing_error')


def check_engine3_eligibility(case, user, db=None) -> dict:
    from .sharing import active_grant
    reasons = []

    if user.get("role") != "advocate":
        reasons.append("Engine 3 is advocate-only.")

    if user.get("verification_status") != "VERIFIED":
        reasons.append("Advocate must be verified.")

    if case.get("assigned_advocate_id") != user.get("id"):
        reasons.append("This case is not assigned to the authenticated advocate.")

    grant = active_grant(db, case.get("case_id"), user.get("id")) if db else None
    if not grant or "case_file" not in grant.get("scopes", []):
        reasons.append("Active citizen consent covering the Case File is required.")

    current_e1 = reviewed_engine1_current(case, db)
    if not current_e1:
        reasons.append("A current advocate-reviewed Engine 1 Case File is required.")

    if case.get("engine1_stale"):
        reasons.append("Engine 1 Case File is stale. Rerun Engine 1 before drafting.")

    canonical = case.get("canonical_case_file") or case.get("case_file") or {}
    if not canonical or not canonical.get("version"):
        reasons.append("Current Engine 1 Case File is missing.")
    elif case.get("advocate_approved_case_file_version") != canonical.get("version"):
        reasons.append("Input Case File version does not match advocate review approval state.")

    if case.get("review_status") not in {"REVIEWED_CURRENT", "ADVOCATE_APPROVED"} and case.get("status") != "ADVOCATE_APPROVED":
        reasons.append("Advocate review must be marked current and approved.")

    e2 = case.get("engine2_report") or case.get("engine2") or {}
    e2_ran = bool(e2) and bool(e2.get("overview_ready") or e2.get("status") == "COMPLETED" or e2.get("run_id"))
    e2_skipped = case.get("engine2_choice") == "DECLINED" or not e2_ran
    e2_is_current = e2_ran and not case.get("engine2_stale")
    e2_disclosure = "Argument analysis was run on the current Case File." if e2_is_current else ENGINE2_NOT_RUN_DISCLOSURE

    corrections = db.list("advocate_case_corrections") if db else []
    unresolved_conflicts = any(c.get("conflict_status") == "CONFLICT_DETECTED" for c in corrections if c.get("case_id") == case.get("case_id"))
    if unresolved_conflicts:
        reasons.append("Unresolved substantive correction conflicts must be resolved before drafting.")

    return {
        "eligible": len(reasons) == 0,
        "case_id": case.get("case_id"),
        "reasons": reasons,
        "checks": {
            "role_advocate": user.get("role") == "advocate",
            "advocate_verified": user.get("verification_status") == "VERIFIED",
            "assigned_advocate": case.get("assigned_advocate_id") == user.get("id"),
            "active_consent": bool(grant and "case_file" in grant.get("scopes", [])),
            "reviewed_engine1_current": current_e1,
            "engine1_not_stale": not case.get("engine1_stale"),
            "version_matches_approval": canonical.get("version") == case.get("advocate_approved_case_file_version"),
            "no_unresolved_conflicts": not unresolved_conflicts,
            "engine2_optional": True,
        },
        "review_status": case.get("review_status", "NOT_REVIEWED"),
        "case_file_version": canonical.get("version"),
        "advocate_approved_case_file_version": case.get("advocate_approved_case_file_version"),
        "engine1_current": current_e1,
        "engine2_status": "COMPLETED" if e2_is_current else ("SKIPPED" if e2_skipped else "NOT_RUN"),
        "engine2_run_id": (e2.get("run_id") or e2.get("id")) if e2_is_current else None,
        "engine2_disclosure": e2_disclosure,
    }
