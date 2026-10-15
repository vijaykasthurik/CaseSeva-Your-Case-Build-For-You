SAFE_PROCESSING_MESSAGE = "We could not complete the requested processing. Your saved information is preserved; you can retry or ask an advocate for help."
SAFE_INPUT_MESSAGE = "Some uploaded information could not be read. Please provide a clearer copy or ask your advocate for help."


def public_processing_error(error):
    if not error:
        return None
    result = {"message": SAFE_PROCESSING_MESSAGE}
    if isinstance(error, dict) and error.get("engine") in {1, 2, 3}:
        result["engine"] = error["engine"]
    return result


def public_evidence(item):
    # Storage locations, diagnostics and future internal fields stay private.
    result = {key: item[key] for key in ("evidence_id", "filename", "content_type", "size", "description", "uploaded_at", "uploaded_by", "source_type", "input_source", "duplicate_of", "evidence_state") if key in item}
    extraction = item.get("extraction") or {}
    if extraction:
        status = extraction.get("status")
        result["extraction"] = {"status": status if status in {"COMPLETED", "PENDING", "FAILED", "RUNNING"} else "PENDING"}
        result["extraction"]["review_required"] = bool(extraction.get("review_required"))
        if status == "COMPLETED":
            result["extraction"]["original_text"] = extraction.get("original_text", "")
        else:
            result["extraction"]["reason"] = SAFE_INPUT_MESSAGE
    return result


def public_statuses(statuses):
    allowed = {"WAITING", "PENDING", "RUNNING", "COMPLETED", "FAILED", "SKIPPED", "PENDING_VERIFICATION", "STALE", "BLOCKED"}
    return {key: value if isinstance(value, str) and value in allowed else "PENDING" for key, value in (statuses or {}).items()}


def client_overview(case: dict, db=None) -> dict:
    from .legal_visibility import current_case_file
    file = current_case_file(case, db)
    if not file and case.get('canonical_case_file'):
        # Authority revalidation may hide law, but never erase completed facts.
        file = {**case['canonical_case_file'], 'applicable_law': [], 'legal_findings': [],
                'authority_versions': {}, 'authority_provenance': {}, 'foundation_complete': False,
                'legal_foundation_status': 'PENDING_SOURCE', 'forum': {}, 'limitation': {}}
    e2 = case.get("engine2", {})
    ran = bool(e2.get("overview_ready")) and e2.get("case_file_version") == file.get("version")
    evaluation = e2.get("neutral_evaluation", {}) if ran else {}
    missing = list(file.get("missing_information", []))
    missing += [SAFE_INPUT_MESSAGE for item in file.get("input_pending", [])]
    requests = e2.get("evidence_challenger", {}).get("document_requests", []) if ran else []
    missing += [item["description"] for item in requests if not item.get("resolved")]
    verified = [item for item in file.get("applicable_law", []) if item.get("verification_status") == "VERIFIED" and not item.get("removed")]
    forum = file.get("forum", {})
    limitation = file.get("limitation", {})
    e2_stale = bool(e2) and not ran
    output = {
        "title": "Client Case Overview", "case_id": case["case_id"], "case_file_version": file.get("version"),
        "summary": file.get("citizen_safe_summary") or file.get("intake", {}).get("narrative") or case.get("client_story", ""),
        "key_facts": [{"text": item.get("text") or item.get("proposition", ""), "source_status": item.get("source_status", "UNVERIFIED")} for item in file.get("facts", []) if not item.get("removed")],
        "timeline": file.get("timeline", []),
        "parties": file.get("parties", []),
        "issues": file.get("issues", []),
        "detected_domains": file.get("domains", {}),
        "applicable_law": [{key: item.get(key) for key in ("provision_id", "title", "explanation", "source_url", "retrieved_at")} for item in verified],
        "pending_advocate_verification": [{"type": item.get("type") if item.get("type") in {"legal_corpus", "temporal_law", "forum", "limitation"} else "legal_verification", "reason": "Your advocate needs to verify the applicable law and its use in your case."} for item in file.get("pending_advocate_verification", [])],
        "forum": forum if forum.get("verification_status") == "VERIFIED" else None,
        "limitation": limitation if limitation.get("verification_status") == "VERIFIED" else None,
        "argument_analysis_run": ran,
        "argument_analysis_note": "Argument analysis was run on the current Case File." if ran else ("Argument analysis was run on an earlier Case File version and is now stale. Rerun Strengthen My Case to update." if e2_stale else "Adversarial case-strengthening analysis was not run on the current Case File."),
        "issue_readiness": evaluation.get("issue_readiness", []) if ran else [],
        "key_risks": evaluation.get("unresolved_risks", []), "missing_details": missing,
        "key_challenges": ([oa.get("summary") for oa in e2.get("opposing_arguments", [])] if e2.get("opposing_arguments") else [ai.get("description") for ai in e2.get("alternative_interpretations", [])]) if ran else [],
        "evidence_gaps": [eg.get("description") for eg in e2.get("evidence_gaps", [])] if ran else [],
        "unresolved_contradictions": [c.get("description") for c in e2.get("contradictions", [])] if ran else [],
        "preparation_actions": e2.get("preparation_actions", []) if ran else [],
        "legal_authority_limitations": e2.get("legal_authority_limitations", []) if ran else [],
        "engine2_stale": e2_stale,
        "ready_to_find_advocate": bool(file) and not case.get("processing_error"),
        "next_step": "Find an advocate for review." if missing or file.get("pending_advocate_verification") else "The case is ready to proceed to an advocate.",
        "processing_mode": file.get("processing_mode"), "documents_outdated": case.get("documents_outdated", False),
        "safe_next_actions": file.get("next_actions", []),
        "legal_foundation_status": file.get("legal_foundation_status", "PENDING_SOURCE" if case.get("legal_foundation_requested") else "NOT_REQUESTED"),
        "pipeline_status": case.get("status"),
    }
    legal_status = output["legal_foundation_status"]
    if legal_status == "VERIFIED_AUTHORITY":
        output["next_step"] = "Verified source research is ready for advocate review."
    elif legal_status == "PENDING_SOURCE":
        output["next_step"] = "Legal foundation is pending independent legal review by an enrolled advocate. Your saved case understanding is preserved."
    elif legal_status == "ABSTAINED":
        output["next_step"] = "The system has abstained from asserting statutory citations. Consult a verified advocate for legal research."
    elif legal_status == "CONFLICTING_AUTHORITY":
        output["next_step"] = "The legal-source picture needs further professional review. Consult a verified advocate."
    if case.get("engine1_execution") == "ORCHESTRATED_CORE_V1":
        state = case.get("case_understanding_status")
        output.update(case_understanding_status=state if state in {"BUILDING", "READY", "REVIEW_REQUIRED", "NEEDS_INPUT"} else "PENDING",
                      ready_to_find_advocate=bool(file) and not case.get("processing_error"))
    return output


def client_case(case: dict, db=None) -> dict:
    # Explicit projection: new internal fields are private by default.
    keys = ("case_id", "public_case_id", "origin", "preferred_language", "journey_stage", "owner_user_id", "created_at", "status", "stage", "stage_details", "client_story", "evidence", "version", "workflow_version", "stage_statuses", "input_statuses", "input_status", "active_engine", "current_stage", "processing_error", "engine2_choice", "assigned_advocate_id", "requested_advocate_id", "documents_outdated", "document_version", "engine2_stale")
    output = {key: case.get(key) for key in keys if key in case}
    output["processing_error"] = public_processing_error(case.get("processing_error") or case.get("analysis_error") or case.get("legal_analysis_error"))
    output["evidence"] = [public_evidence(item) for item in case.get("evidence", [])]
    for field in ("stage_statuses", "input_statuses"):
        output[field] = public_statuses(case.get(field))
    output["overview"] = client_overview(case, db)
    output["engine1_available"] = bool(case.get("case_file"))
    if case.get("engine1_execution") == "ORCHESTRATED_CORE_V1":
        state = case.get("case_understanding_status")
        output["case_understanding_status"] = state if state in {"BUILDING", "READY", "REVIEW_REQUIRED", "NEEDS_INPUT"} else "PENDING"
        output["legal_foundation_status"] = output['overview']['legal_foundation_status']
        output['engine1_available'] = bool(output['overview']['case_file_version']) and bool(case.get('legal_case_file_current'))
        if case.get('legal_foundation_requested') and case.get('legal_foundation_status') == 'READY' and not output['engine1_available']:
            output['status'] = 'LEGAL_FOUNDATION_REVIEW_REQUIRED'
    output["client_messages"] = [item for item in case.get("professional_notes", []) if item.get("visibility") == "SHARED_WITH_CLIENT"]
    output["information_requests"] = case.get("information_requests", [])
    output["filing_update"] = case.get("filing_update")
    batches = case.get("clarification_rounds", [])
    if batches and batches[-1].get("answering_user_id") == case["owner_user_id"]:
        batch = batches[-1]
        output["clarification"] = batch
        if batch.get('core'):
            output['clarification'] = {key: batch[key] for key in ('round', 'batch_id', 'status', 'created_at', 'answers') if key in batch}
            output['clarification']['questions'] = [{key: q[key] for key in ('question_id', 'question', 'control', 'choices', 'priority') if key in q} for q in batch['questions']]
    return output
