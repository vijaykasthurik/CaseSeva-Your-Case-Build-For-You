from ..adapters.capabilities import llm_is_mock
import re
import threading
import time
from typing import Any

from pydantic import ValidationError

from ..adapters.legal_retrieval import normalize_domain_to_corpus
from ..models.legal import (
    ChallengerOutput,
    CitationOutput,
    ClaimantOutput,
    DomainOutput,
    EvidenceMappingOutput,
    ForumOutput,
    IssuesOutput,
    LimitationOutput,
    NeutralOutput,
    OpponentOutput,
    RebuttalOutput,
    StatuteOutput,
)

LEGAL_STAGES = [
    "DOMAIN_ROUTER",
    "LEGAL_ISSUE_IDENTIFICATION",
    "STATUTE_RETRIEVAL",
    "CITATION_VERIFICATION",
    "JURISDICTION_FORUM",
    "LIMITATION_CHECK",
    "EVIDENCE_ISSUE_MAPPING",
    "CLAIMANT_COUNSEL",
    "OPPONENT_COUNSEL",
    "EVIDENCE_CHALLENGER",
    "REBUTTAL",
    "NEUTRAL_EVALUATION",
]

SCHEMAS = {
    "DOMAIN_ROUTER": DomainOutput,
    "LEGAL_ISSUE_IDENTIFICATION": IssuesOutput,
    "STATUTE_RETRIEVAL": StatuteOutput,
    "CITATION_VERIFICATION": CitationOutput,
    "JURISDICTION_FORUM": ForumOutput,
    "LIMITATION_CHECK": LimitationOutput,
    "EVIDENCE_ISSUE_MAPPING": EvidenceMappingOutput,
    "CLAIMANT_COUNSEL": ClaimantOutput,
    "OPPONENT_COUNSEL": OpponentOutput,
    "EVIDENCE_CHALLENGER": ChallengerOutput,
    "REBUTTAL": RebuttalOutput,
    "NEUTRAL_EVALUATION": NeutralOutput,
}


def schema_for(stage: str) -> dict[str, Any]:
    return {"stage": stage.lower(), "schema": stage}


def validate_response(stage: str, response: dict[str, Any]):
    return SCHEMAS[stage].model_validate(response)


def _write_stage(changes: dict[str, Any], stage: str, output: Any) -> None:
    payload = output.model_dump()
    if stage == "DOMAIN_ROUTER":
        changes["legal_domain"] = payload
    elif stage == "LEGAL_ISSUE_IDENTIFICATION":
        changes["legal_issues"] = payload["issues"]
    elif stage == "STATUTE_RETRIEVAL":
        changes["legal_sections"] = payload
    elif stage == "CITATION_VERIFICATION":
        changes["citation_verification"] = payload
        decisions = {item["provision_id"]: item["decision"] for item in payload["decisions"]}
        sections = changes.get("legal_sections", {}).get("selected", [])
        if "verified_legal_sections" not in changes:
            changes["verified_legal_sections"] = [
                section for section in sections if decisions.get(section["provision_id"]) == "VERIFIED"
            ]

    elif stage == "JURISDICTION_FORUM":
        changes["forum"] = payload
    elif stage == "LIMITATION_CHECK":
        changes["limitation"] = payload
    elif stage == "EVIDENCE_ISSUE_MAPPING":
        changes["evidence_issue_mapping"] = payload["mappings"]
    elif stage == "CLAIMANT_COUNSEL":
        changes.setdefault("arguments", {})["claimant"] = payload
    elif stage == "OPPONENT_COUNSEL":
        changes.setdefault("arguments", {})["opponent"] = payload
    elif stage == "EVIDENCE_CHALLENGER":
        changes.setdefault("arguments", {})["evidence_challenger"] = payload
        changes["document_requests"] = payload["document_requests"]
    elif stage == "REBUTTAL":
        changes.setdefault("arguments", {})["rebuttal"] = payload
    elif stage == "NEUTRAL_EVALUATION":
        changes["neutral_evaluation"] = payload


def build_legal_prompt(stage: str, current: dict[str, Any]) -> str:
    story = current.get("client_story", "").strip()
    evidence = current.get("evidence", [])
    evidence_str = "\n".join([f"- [{e.get('evidence_id')}] {e.get('filename')}: {e.get('description', '')}" for e in evidence]) or "None"
    facts = current.get("facts", [])
    facts_str = "\n".join([f"- [{f.get('fact_id')}] {f.get('text')}" for f in facts]) or "None"
    timeline = current.get("timeline", [])
    timeline_str = "\n".join([f"- [{t.get('event_id')}] {t.get('date')}: {t.get('description')}" for t in timeline]) or "None"
    parties = current.get("parties", {})
    parties_str = f"Client Role: {parties.get('client_role')}, Opposite Party: {parties.get('opposite_party')}, Relationship: {parties.get('relationship')}" if parties else "None"
    
    issues = current.get("legal_issues", [])
    issues_str = "\n".join([f"- [{i.get('issue_id')}] {i.get('question')}" for i in issues]) or "None"
    
    sections_raw = current.get("legal_sections", {})
    sections = sections_raw.get("selected", []) if isinstance(sections_raw, dict) else (sections_raw if isinstance(sections_raw, list) else [])
    sections_str = "\n".join([f"- [{s.get('provision_id')}] {s.get('title')}: {s.get('explanation')}" for s in sections]) or "None"
    
    forum = current.get("forum", {})
    forum_str = f"Forum Family: {forum.get('forum_family')}, Commission Level: {forum.get('commission_level')}, Basis: {forum.get('territorial_basis')}" if forum else "None"
    
    args = current.get("arguments", {})
    claimant_pts = args.get("claimant", {}).get("points", []) if isinstance(args.get("claimant"), dict) else []
    claimant_str = "\n".join([f"- {p}" for p in claimant_pts]) or "None"
    
    opponent_objs = args.get("opponent", {}).get("objections", []) if isinstance(args.get("opponent"), dict) else []
    opponent_str = "\n".join([f"- [{o.get('objection_id')}] {o.get('text')}" for o in opponent_objs]) or "None"
    
    challenger_attacks = args.get("evidence_challenger", {}).get("attacks", []) if isinstance(args.get("evidence_challenger"), dict) else []
    challenger_str = "\n".join([f"- {a}" for a in challenger_attacks]) or "None"

    if stage == "DOMAIN_ROUTER":
        return (
            f"Classify the legal domain of this Indian legal dispute.\n\n"
            f"CLIENT STORY:\n{story}\n\n"
            f"EXTRACTED FACTS:\n{facts_str}"
        )
    elif stage == "LEGAL_ISSUE_IDENTIFICATION":
        return (
            f"Identify all legal issues raised by the facts and evidence in this dispute.\n\n"
            f"CLIENT STORY:\n{story}\n\n"
            f"EXTRACTED FACTS:\n{facts_str}\n\n"
            f"UPLOADED EVIDENCE:\n{evidence_str}"
        )
    elif stage == "STATUTE_RETRIEVAL":
        # NOTE: corpus_candidates must be injected by the caller via current["_corpus_candidates"]
        candidates = current.get("_corpus_candidates", [])
        candidates_str = "\n".join(
            f"- [{c['provision_id']}] {c['title']}: {c['summary']} (Source: {c.get('source_url', '')})"
            for c in candidates
        ) or "None retrieved from corpus"
        return (
            f"Select the provisions below that are directly applicable to this dispute.\n"
            f"CRITICAL REQUIREMENT: You MUST ONLY select provisions from the CANDIDATE PROVISIONS list provided below. "
            f"Do NOT recall, invent, or output any statutory provision, section number, or legal rule from your internal memory.\n\n"
            f"CLIENT STORY:\n{story}\n\n"
            f"EXTRACTED FACTS:\n{facts_str}\n\n"
            f"LEGAL ISSUES:\n{issues_str}\n\n"
            f"CANDIDATE PROVISIONS (these are the ONLY provisions you may select from):\n{candidates_str}"
        )
    elif stage == "CITATION_VERIFICATION":
        # NOTE: corpus_candidates must be injected by the caller via current["_corpus_candidates"]
        candidates = current.get("_corpus_candidates", [])
        corpus_index = {c["provision_id"]: c for c in candidates}
        selected_provisions = (
            current.get("legal_sections", {}).get("selected", [])
            if isinstance(current.get("legal_sections"), dict)
            else []
        )
        verified_sections = [s for s in selected_provisions if s.get("provision_id") in corpus_index]
        sections_to_verify = "\n".join(
            f"- [{s['provision_id']}] {corpus_index[s['provision_id']]['title']}: {s.get('explanation', corpus_index[s['provision_id']]['summary'])}"
            for s in verified_sections
        ) or "None (all statute_retrieval provisions were missing from corpus)"
        return (
            f"For each provision below, decide VERIFIED or REJECTED based solely on whether the facts support the provision's claim.\n"
            f"You MUST output a decision for every provision listed — no extras, no omissions.\n\n"
            f"EXTRACTED FACTS:\n{facts_str}\n\n"
            f"PROVISIONS TO VERIFY:\n{sections_to_verify}"
        )
    elif stage == "JURISDICTION_FORUM":
        return (
            f"Determine the appropriate legal forum, commission level, and territorial jurisdiction under Indian law.\n\n"
            f"CLIENT STORY:\n{story}\n\n"
            f"EXTRACTED FACTS:\n{facts_str}\n\n"
            f"PARTIES:\n{parties_str}"
        )
    elif stage == "LIMITATION_CHECK":
        return (
            f"Assess whether the claim is within the statutory limitation period under Indian law.\n\n"
            f"TIMELINE OF EVENTS:\n{timeline_str}\n\n"
            f"EXTRACTED FACTS:\n{facts_str}"
        )
    elif stage == "EVIDENCE_ISSUE_MAPPING":
        return (
            f"Map each legal issue to the uploaded evidence items.\n\n"
            f"LEGAL ISSUES:\n{issues_str}\n\n"
            f"EXTRACTED FACTS:\n{facts_str}\n\n"
            f"UPLOADED EVIDENCE:\n{evidence_str}"
        )
    elif stage == "CLAIMANT_COUNSEL":
        return (
            f"Develop strong, concise legal arguments supporting the claimant.\n"
            f"CONSTRAINTS:\n"
            f"- Provide at most 5 key argument points.\n"
            f"- Keep each point concise (maximum 2-3 sentences).\n\n"
            f"CLIENT STORY:\n{story}\n\n"
            f"EXTRACTED FACTS:\n{facts_str}\n\n"
            f"LEGAL ISSUES:\n{issues_str}\n\n"
            f"VERIFIED PROVISIONS:\n{sections_str}\n\n"
            f"FORUM:\n{forum_str}"
        )
    elif stage == "OPPONENT_COUNSEL":
        return (
            f"Anticipate potential legal objections and defenses from the opposing party.\n"
            f"CONSTRAINTS:\n"
            f"- Formulate at most 5 key objections.\n"
            f"- Keep each objection concise (maximum 2-3 sentences).\n\n"
            f"EXTRACTED FACTS:\n{facts_str}\n\n"
            f"LEGAL ISSUES:\n{issues_str}\n\n"
            f"CLAIMANT ARGUMENTS:\n{claimant_str}"
        )
    elif stage == "EVIDENCE_CHALLENGER":
        return (
            f"Analyze evidentiary weaknesses, potential attacks from the opponent, and any needed missing documents.\n\n"
            f"EXTRACTED FACTS:\n{facts_str}\n\n"
            f"UPLOADED EVIDENCE:\n{evidence_str}\n\n"
            f"OPPONENT OBJECTIONS:\n{opponent_str}"
        )
    elif stage == "REBUTTAL":
        return (
            f"Formulate persuasive, concise rebuttals to address top opponent objections.\n"
            f"CONSTRAINTS:\n"
            f"- Address at most 5 key opponent objections.\n"
            f"- Keep each rebuttal response concise (maximum 2-3 sentences per objection).\n\n"
            f"CLAIMANT ARGUMENTS:\n{claimant_str}\n\n"
            f"OPPONENT OBJECTIONS:\n{opponent_str}\n\n"
            f"EVIDENCE ATTACKS:\n{challenger_str}"
        )
    elif stage == "NEUTRAL_EVALUATION":
        return (
            f"Provide an objective evaluation summarizing case strengths, weaknesses, and unresolved risks.\n\n"
            f"CLIENT STORY:\n{story}\n\n"
            f"EXTRACTED FACTS:\n{facts_str}\n\n"
            f"LEGAL ISSUES:\n{issues_str}\n\n"
            f"CLAIMANT ARGUMENTS:\n{claimant_str}\n\n"
            f"OPPONENT OBJECTIONS:\n{opponent_str}"
        )
    return f"Return legal analysis for {stage}."


from difflib import SequenceMatcher


def normalize_section_num(sec_str: str) -> str:
    cleaned = re.sub(r"^[A-Z0-9]+-", "", sec_str).strip()
    cleaned = re.sub(r"(?i)\b(?:Section|Sec|\.)\b", "", cleaned).strip()
    cleaned = re.sub(r"\s*\(\s*", "(", cleaned)
    cleaned = re.sub(r"\s*\)\s*", ")", cleaned)
    cleaned = re.sub(r"\s+", "", cleaned)
    return cleaned


def normalize_title(title_str: str) -> str:
    title_clean = re.sub(r"^[A-Z0-9]+-", "", title_str)
    title_clean = re.sub(r"(?i)^(?:Section|Sec\.)?\s*\d+[A-Z]?(?:\([0-9a-z]+\))?\s*[-–—:]?\s*", "", title_clean)
    title_clean = re.sub(r"[^\w\s]", "", title_clean.lower()).strip()
    return title_clean


def title_similarity(t1: str, t2: str) -> float:
    return SequenceMatcher(None, normalize_title(t1), normalize_title(t2)).ratio()


def corpus_filter_provisions(provisions: list[dict], corpus: list[dict]) -> list[dict]:
    """Hard filter: drop any provision whose provision_id / section number is not grounded in fetched text.
    Enforces authoritative corpus/fetched title and source_url."""
    corpus_map = {entry["provision_id"]: entry for entry in corpus}
    norm_map = {normalize_section_num(entry["provision_id"]): entry for entry in corpus}
    filtered = []
    for p in provisions:
        pid = p.get("provision_id") if isinstance(p, dict) else getattr(p, "provision_id", None)
        norm_pid = normalize_section_num(pid or "")
        entry = corpus_map.get(pid) or norm_map.get(norm_pid)
        if entry:
            p_dict = p.model_dump() if hasattr(p, "model_dump") else dict(p)
            p_dict["title"] = entry["title"]
            p_dict["source_url"] = entry.get("source_url", p_dict.get("source_url", ""))
            filtered.append(p_dict)
    return filtered


def run_legal_pipeline(app, case_id: str, preserve_advocate_review: bool = False, retry_failed: bool = False, requested_stages: list[str] | None = None) -> None:
    db = app.state.adapters.database
    try:
        workflow = app.state.adapters.workflow
        llm = app.state.adapters.llm
        case = db.get("cases", case_id)
        if not case:
            return
        selected = requested_stages or LEGAL_STAGES
        preserve_advocate_review = preserve_advocate_review or case.get("status") in {"ADVOCATE_REVIEW", "ADVOCATE_APPROVED"}
        run = workflow.start_run(case_id, selected)
        current = db.get("cases", case_id)
        statuses = dict(current.get("stage_statuses", {}))
        for stage in selected:
            statuses[stage] = "WAITING"
        db.update("cases", case_id, {
            "status": "ADVOCATE_REVIEW" if preserve_advocate_review else "LEGAL_ANALYSIS_RUNNING",
            "stage_statuses": statuses,
            "legal_workflow_run_id": run["id"],
            "version": current.get("version", 1) + 1,
        })
        for stage in selected:
            current = db.get("cases", case_id)
            statuses = dict(current.get("stage_statuses", {}))
            statuses[stage] = "RUNNING"
            db.update("cases", case_id, {"stage_statuses": statuses, "version": current.get("version", 1) + 1})
            try:
                time.sleep(0.05)
                schema = schema_for(stage)
                if llm_is_mock(app.state.adapters):
                    if stage == "DOMAIN_ROUTER":
                        if "[NON_CONSUMER]" in current.get("client_story", ""):
                            schema["fixture"] = "other_domain"
                        elif any(k in current.get("client_story", "").lower() for k in ["salary", "wages", "employment", "labor", "labour"]):
                            schema["fixture"] = "labor_domain"
                    if stage == "STATUTE_RETRIEVAL" and "[HALLUCINATED_STATUTE]" not in current.get("client_story", ""):
                        norm_domain = normalize_domain_to_corpus(str(current.get("legal_domain", {}).get("domain", "")))
                        if norm_domain == "labour" or any(k in current.get("client_story", "").lower() for k in ["salary", "wages", "employment", "labor", "labour"]):
                            schema["fixture"] = "statute_retrieval_labor"
                    if "[LEGAL_MALFORMED]" in current.get("client_story", "") and stage == "LEGAL_ISSUE_IDENTIFICATION":
                        schema["fixture"] = "malformed"
                    if "[HALLUCINATED_STATUTE]" in current.get("client_story", "") and stage == "STATUTE_RETRIEVAL":
                        schema["fixture"] = "hallucinated_statute"
                corpus_candidates: list[dict] = []
                detected_domain = current.get("legal_domain", {}).get("domain", "")
                if stage in {"STATUTE_RETRIEVAL", "CITATION_VERIFICATION"}:
                    query = " ".join(
                        issue.get("question", "") for issue in current.get("legal_issues", [])
                    ) or "wages defect claim replacement refund jurisdiction limitation"
                    corpus_candidates = app.state.adapters.legal_retrieval.search(query, limit=10, domain=detected_domain)
                    # Inject into current so build_legal_prompt can use them
                    current = dict(current)
                    current["_corpus_candidates"] = corpus_candidates
                if stage == "EVIDENCE_CHALLENGER" and any(item.get("resolved") for item in current.get("document_requests", [])):
                    schema["fixture"] = "no_document"
                elif stage == "EVIDENCE_CHALLENGER" and "[NEEDS_DOCUMENT]" in current.get("client_story", ""):
                    schema["fixture"] = "document_request"
                prompt = build_legal_prompt(stage, current)
                response = llm.generate(prompt, schema)
                output = validate_response(stage, response)
                
                # Graceful degradation for unsupported domains without verified corpus or retrievable sources
                if not corpus_candidates and normalize_domain_to_corpus(detected_domain) is None:
                    if stage == "STATUTE_RETRIEVAL":
                        from ..models.legal import StatuteOutput
                        output = StatuteOutput(selected=[], rejected=[], note=f"No verified statutory sources retrieved for domain: {detected_domain}")
                    elif stage == "JURISDICTION_FORUM":
                        from ..models.legal import ForumOutput
                        output = ForumOutput(forum_family="UNSUPPORTED_DOMAIN", commission_level=f"No verified forum rules for domain: {detected_domain}", territorial_basis="Address verification required")
                    elif stage == "LIMITATION_CHECK":
                        from ..models.legal import LimitationOutput
                        output = LimitationOutput(result="UNKNOWN", explanation=f"No verified limitation rules for domain: {detected_domain}")

                # Hard corpus filter: strip any hallucinated provision IDs after STATUTE_RETRIEVAL
                if stage == "STATUTE_RETRIEVAL" and corpus_candidates:
                    if True:  # User content can never disable grounding checks.
                        filtered_selected = corpus_filter_provisions(
                            [p.model_dump() if hasattr(p, "model_dump") else p for p in output.selected],
                            corpus_candidates,
                        )
                        from ..models.legal import StatuteOutput, ProvisionProposal
                        output = StatuteOutput(
                            selected=[ProvisionProposal(**p) for p in filtered_selected],
                            rejected=output.rejected,
                        )
                        if not output.selected:
                            raise ValueError(
                                f"Corpus filter dropped all provisions for domain: {detected_domain}"
                            )

                current = db.get("cases", case_id)
                changes: dict[str, Any] = {"version": current.get("version", 1) + 1}
                changes["arguments"] = dict(current.get("arguments", {}))
                if stage == "CITATION_VERIFICATION":
                    changes["legal_sections"] = current.get("legal_sections", {})
                    if corpus_candidates:
                        corpus_index = {c["provision_id"]: c for c in corpus_candidates}
                        norm_index = {normalize_section_num(c["provision_id"]): c for c in corpus_candidates}

                        selected_provisions = (
                            current.get("legal_sections", {}).get("selected", [])
                            if isinstance(current.get("legal_sections"), dict)
                            else []
                        )
                        selected_map = {p.get("provision_id"): p for p in selected_provisions}
                        decisions_by_id = {d.provision_id: d for d in output.decisions}
                        
                        from ..models.legal import CitationDecision, CitationOutput
                        validated_decisions = []
                        
                        all_pids = list(dict.fromkeys(list(selected_map.keys()) + [d.provision_id for d in output.decisions]))
                        for pid in all_pids:
                            norm_pid = normalize_section_num(pid)
                            corpus_entry = corpus_index.get(pid) or norm_index.get(norm_pid)
                            if not corpus_entry:
                                validated_decisions.append(CitationDecision(
                                    provision_id=pid,
                                    decision="REJECTED",
                                    reason="Provision ID not found in fetched legal document text — hallucinated by model.",
                                ))
                                continue

                            selected_item = selected_map.get(pid, {})
                            selected_title = selected_item.get("title", "").strip()
                            corpus_title = corpus_entry.get("title", "").strip()

                            sim = title_similarity(selected_title, corpus_title)
                            if selected_title and sim < 0.85:
                                validated_decisions.append(CitationDecision(
                                    provision_id=pid,
                                    decision="REJECTED",
                                    reason=f"Title mismatch: '{selected_title}' does not match fetched title '{corpus_title}' (similarity {sim:.2f} < 0.85 threshold).",
                                ))
                            elif pid in decisions_by_id:
                                validated_decisions.append(decisions_by_id[pid])
                            else:
                                validated_decisions.append(CitationDecision(
                                    provision_id=pid,
                                    decision="VERIFIED",
                                    reason=f"Grounded: Provision {pid} grounded in fetched text.",
                                ))
                        output = CitationOutput(decisions=validated_decisions)

                _write_stage(changes, stage, output)
                statuses = dict(current.get("stage_statuses", {}))
                statuses[stage] = "COMPLETED"
                changes["stage_statuses"] = statuses
                if stage == "EVIDENCE_CHALLENGER" and any(not item.resolved for item in output.document_requests):
                    changes["status"] = "NEEDS_DOCUMENT"
                db.update("cases", case_id, changes)
                workflow.advance_run(run["id"])
                if stage == "DOMAIN_ROUTER" and normalize_domain_to_corpus(output.domain) is None:
                    db.update("cases", case_id, {
                        "status": "OUT_OF_SCOPE",
                        "out_of_scope_message": f"Statutory grounding is not currently configured for domain '{output.domain}'. An advocate should review this matter.",
                        "forum": {"forum_family": "UNSUPPORTED_DOMAIN", "commission_level": "No verified forum rules for domain", "territorial_basis": "Address verification required"},
                        "limitation": {"result": "UNKNOWN", "explanation": "No verified limitation rules for domain"},
                        "version": db.get("cases", case_id).get("version", 1) + 1,
                    })
                    return
                if stage == "EVIDENCE_CHALLENGER" and any(not item.resolved for item in output.document_requests):
                    return
            except Exception as exc:
                import traceback
                traceback.print_exc()
                current = db.get("cases", case_id)
                statuses = dict(current.get("stage_statuses", {}))
                statuses[stage] = "FAILED"
                db.update("cases", case_id, {
                    "stage_statuses": statuses,
                    "legal_analysis_error": {"stage": stage, "message": str(exc)},
                    "status": "LEGAL_ANALYSIS_FAILED",
                    "version": current.get("version", 1) + 1,
                })
                return
        current = db.get("cases", case_id)
        if all(current.get("stage_statuses", {}).get(stage) == "COMPLETED" for stage in selected):
            db.update("cases", case_id, {
                "status": "ADVOCATE_REVIEW" if preserve_advocate_review else "AWAITING_PREVIEW_2",
                "version": current.get("version", 1) + 1,
            })
    except Exception as exc:
        # Top-level catch-all: if anything fails before/outside the stage loop,
        # mark the case as failed rather than leaving it stuck at RUNNING.
        import traceback
        traceback.print_exc()
        try:
            db.update("cases", case_id, {
                "status": "LEGAL_ANALYSIS_FAILED",
                "legal_analysis_error": {"stage": "INIT", "message": str(exc)},
            })
        except Exception:
            pass  # DB itself is broken — nothing more we can do



def start_legal_async(app, case_id: str, preserve_advocate_review: bool = False, retry_failed: bool = False, requested_stages: list[str] | None = None) -> None:
    import os
    lambda_name = os.getenv("AWS_LAMBDA_FUNCTION_NAME")
    if lambda_name:
        import json
        import boto3
        region = os.getenv("CASESEVA_AWS_REGION") or os.getenv("AWS_REGION", "ap-southeast-2")
        client = boto3.client("lambda", region_name=region)
        payload = {
            "action": "run_legal_pipeline",
            "case_id": case_id,
            "preserve_advocate_review": preserve_advocate_review,
            "retry_failed": retry_failed,
            "requested_stages": requested_stages,
        }
        client.invoke(
            FunctionName=lambda_name,
            InvocationType="Event",
            Payload=json.dumps(payload),
        )
    else:
        thread = threading.Thread(target=run_legal_pipeline, args=(app, case_id, preserve_advocate_review, retry_failed, requested_stages), daemon=True)
        thread.start()
