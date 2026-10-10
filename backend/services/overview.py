def public_processing_error(error):
    if error and error.get("engine") in {2, 3}:
        return {"engine": error["engine"], "stage": error.get("stage"), "message": "Processing could not be completed. Your advocate can review the details and retry."}
    return error


def client_overview(case: dict) -> dict:
    file = case.get("case_file", {})
    ran = bool(case.get("engine2", {}).get("overview_ready")) and case.get("engine2", {}).get("case_file_version") == file.get("version")
    evaluation = case.get("engine2", {}).get("neutral_evaluation", {}) if ran else {}
    missing = list(file.get("missing_information", []))
    missing += [item.get("reason", "Unreadable evidence") for item in file.get("input_pending", [])]
    requests = case.get("engine2", {}).get("evidence_challenger", {}).get("document_requests", [])
    missing += [item["description"] for item in requests if not item.get("resolved")]
    verified = [item for item in file.get("applicable_law", []) if item.get("verification_status") == "VERIFIED" and not item.get("removed")]
    forum = file.get("forum", {})
    limitation = file.get("limitation", {})
    return {
        "title": "Client Case Overview", "case_id": case["case_id"], "case_file_version": file.get("version"),
        "summary": file.get("intake", {}).get("narrative") or case.get("client_story", ""),
        "key_facts": [{"text": item["text"], "source_status": item.get("source_status", "UNVERIFIED")} for item in file.get("facts", []) if not item.get("removed")],
        "applicable_law": [{key: item.get(key) for key in ("provision_id", "title", "explanation", "source_url", "retrieved_at")} for item in verified],
        "pending_advocate_verification": file.get("pending_advocate_verification", []),
        "forum": forum if forum.get("verification_status") == "VERIFIED" else None,
        "limitation": limitation if limitation.get("verification_status") == "VERIFIED" else None,
        "argument_analysis_run": ran,
        "argument_analysis_note": "Argument analysis was run on the current Case File." if ran else "Adversarial case-strengthening analysis was not run on the current Case File.",
        "issue_readiness": evaluation.get("issue_readiness", []) if ran else [],
        "key_risks": evaluation.get("unresolved_risks", []), "missing_details": missing,
        "ready_to_find_advocate": bool(file) and not case.get("processing_error"),
        "next_step": "Find an advocate for review." if missing or file.get("pending_advocate_verification") else "The case is ready to proceed to an advocate.",
        "processing_mode": file.get("processing_mode"), "documents_outdated": case.get("documents_outdated", False),
    }


def client_case(case: dict) -> dict:
    # Explicit projection: new internal fields are private by default.
    keys = ("case_id", "owner_user_id", "created_at", "status", "stage", "stage_details", "client_story", "evidence", "version", "workflow_version", "stage_statuses", "input_statuses", "active_engine", "current_stage", "processing_error", "engine2_choice", "assigned_advocate_id", "requested_advocate_id", "documents_outdated", "document_version", "engine2_stale")
    output = {key: case.get(key) for key in keys if key in case}
    output["processing_error"] = public_processing_error(case.get("processing_error"))
    output["overview"] = client_overview(case)
    output["engine1_available"] = bool(case.get("case_file"))
    return output
