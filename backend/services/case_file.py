"""Canonical Engine-1 Case File contract and assembly.

Integrates all completed Engine-1 components into one reliable,
case-driven end-to-end pipeline:
Case Understanding -> Facts / Timeline / Parties / Evidence
                   -> Issues -> Dynamic Domains -> Dynamic Specialists
                   -> Retrieval -> Legal Foundation -> Reconciliation
                   -> Canonical Case File -> Citizen Case Overview

"The case determines the AI team — not a fixed workflow."
"""
from typing import Any, Literal
from ..models.case import utc_now
from .case_blackboard import versions, digest
from .legal_visibility import authority_manifest

LEGAL_STATUS = Literal[
    "VERIFIED_AUTHORITY",
    "PENDING_SOURCE",
    "ABSTAINED",
    "CONFLICTING_AUTHORITY",
    "NOT_REQUESTED",
]

def compact_facts(facts_dict: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for fid, f in sorted((facts_dict or {}).items()):
        if f.get("superseded"):
            continue
        items.append({
            "fact_id": fid,
            "text": f.get("proposition", ""),
            "proposition": f.get("proposition", ""),
            "category": f.get("category", "GENERAL"),
            "date": f.get("date"),
            "exact_values": f.get("exact_values", []),
            "certainty": f.get("certainty", "STATED"),
            "source_status": f.get("source_status", "UNVERIFIED"),
            "verification_status": f.get("verification", "UNVERIFIED"),
            "evidence_ids": f.get("evidence_ids", []),
            "source_ids": f.get("source_ids", []),
        })
    return items


def compact_timeline(timeline_dict: dict[str, Any], incidents_dict: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    source = timeline_dict or incidents_dict or {}
    for tid, item in sorted(source.items()):
        if item.get("superseded"):
            continue
        items.append({
            "timeline_id": tid,
            "event_id": tid,
            "description": item.get("description", ""),
            "date": item.get("date"),
            "fact_ids": item.get("fact_ids", []),
            "party_ids": item.get("party_ids", []),
            "unknown_fields": item.get("unknown_fields", []),
        })
    return items


def compact_parties(parties_dict: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for pid, p in sorted((parties_dict or {}).items()):
        if p.get("superseded"):
            continue
        items.append({
            "party_id": pid,
            "name": p.get("name") or p.get("normalized_name"),
            "role": p.get("role", "PARTICIPANT"),
            "fact_ids": p.get("fact_ids", []),
            "unknown_attributes": p.get("unknown_attributes", []),
            "verification": p.get("verification", "UNVERIFIED"),
        })
    return items


def compact_relationships(relationships_dict: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for rid, r in sorted((relationships_dict or {}).items()):
        items.append({
            "relationship_id": rid,
            "left": r.get("left"),
            "right": r.get("right"),
            "relationship": r.get("relationship", "CONNECTED"),
            "fact_ids": r.get("fact_ids", []),
        })
    return items


def compact_evidence_mappings(evidence_mapping: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    links = evidence_mapping.get("links", []) if isinstance(evidence_mapping, dict) else []
    for link in links:
        items.append({
            "evidence_id": link.get("evidence_id"),
            "fact_id": link.get("fact_id"),
            "relationship_type": link.get("relationship_type", "SUPPORTS"),
            "passage": link.get("passage"),
        })
    return items


def compact_clarification(clarification_rounds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    for round_item in clarification_rounds or []:
        for q in round_item.get("questions", []):
            qid = q.get("question_id")
            answer = next((a for a in round_item.get("answers", []) if a.get("question_id") == qid), None)
            items.append({
                "question_id": qid,
                "topic": q.get("topic", ""),
                "question": q.get("question", ""),
                "priority": q.get("priority", "NORMAL"),
                "answered": answer is not None,
                "answer_response": answer.get("response") if answer else None,
                "answer_value": answer.get("value") if answer else None,
            })
    return items


def compact_issues(legal_issues_dict: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for lid, issue in sorted((legal_issues_dict or {}).items()):
        if issue.get("superseded"):
            continue
        items.append({
            "legal_issue_id": lid,
            "key": issue.get("key"),
            "statement": issue.get("statement", ""),
            "category": issue.get("category", ""),
            "domain": issue.get("domain", ""),
            "domain_contexts": issue.get("domain_contexts", []),
            "fact_ids": issue.get("fact_ids", []),
            "specialist_origins": issue.get("specialist_origins", []),
            "query": issue.get("query", ""),
            "jurisdiction": issue.get("jurisdiction"),
            "limitation_relevant": issue.get("limitation_relevant", False),
            "precedent_useful": issue.get("precedent_useful", False),
            "unknowns": issue.get("unknowns", []),
        })
    return items


def build_citizen_summary(narrative: str, facts: list[dict[str, Any]], domain_info: dict[str, Any]) -> str:
    """Plain-language case summary: what happened without legal jargon."""
    if not facts and not narrative:
        return "No case facts recorded."
    domain = domain_info.get("primary_domain", "GENERAL")
    propositions = [f["text"] for f in facts[:4] if f.get("text")]
    if propositions:
        summary_core = " ".join(propositions)
    else:
        summary_core = (narrative.strip()[:300] + "...") if len(narrative) > 300 else narrative.strip()
    return f"Matter concerning {domain}: {summary_core}"


def build_safe_next_actions(legal_status: str, missing: list[str]) -> list[str]:
    """Safe, non-advisory next steps for citizen."""
    actions = [
        "Review the structured case facts and timeline for factual accuracy.",
        "Preserve all original receipts, communications, and delivery documents in an immutable state.",
    ]
    if missing:
        actions.append(f"Gather available supporting information: {', '.join(missing[:3])}.")
    if legal_status == "VERIFIED_AUTHORITY":
        actions.append("Consult an advocate enrolled with the Bar Council to review verified primary authorities and discuss legal strategy.")
    elif legal_status == "PENDING_SOURCE":
        actions.append("Official statutory texts were identified but remain PENDING genuine Bar Council-enrolled advocate review. Independent human legal review is required before taking formal action.")
    else:
        actions.append("The system has abstained from asserting legal conclusions. Consult an enrolled advocate for legal research and representation.")
    actions.append("Note: CaseSeva does not provide win probabilities, outcome guarantees, or formal legal advice.")
    return actions


def assemble_canonical_case_file(db, case_id: str, board: dict[str, Any], corpus=None) -> dict[str, Any]:
    """Assembles a canonical Engine-1 Case File from blackboard state.

    Preserves completed factual reasoning, domain routing, specialist outputs,
    and issues, while strictly enforcing fail-closed legal authority rules.
    """
    case = db.get("cases", case_id) or {}
    data = board.get("data", {})
    raw = case.get("raw_package") or {}

    facts_dict = data.get("facts", {})
    incidents_dict = data.get("incidents", {})
    timeline_dict = data.get("timeline", {})
    parties_dict = data.get("parties", {})
    relationships_dict = data.get("relationships", {})
    evidence_mapping = data.get("evidence_mapping", {})
    domain_info = data.get("domain_classification", {})
    legal_issues_dict = data.get("legal_issues", {})
    specialists_dict = data.get("specialists", {})
    foundation = data.get("legal_foundation") or {}

    facts = compact_facts(facts_dict)
    disputed_facts = [f for f in facts if f.get("certainty") in {"CONFLICTED", "UNKNOWN"}]
    timeline = compact_timeline(timeline_dict, incidents_dict)
    parties = compact_parties(parties_dict)
    relationships = compact_relationships(relationships_dict)
    evidence_mappings = compact_evidence_mappings(evidence_mapping)

    # Evidence inventory
    evidence_inventory = [
        {
            "evidence_id": item.get("evidence_id"),
            "filename": item.get("filename"),
            "content_type": item.get("content_type"),
            "size": item.get("size"),
            "description": item.get("description", ""),
            "readable": item.get("extraction", {}).get("status") == "COMPLETED",
            "uploaded_at": item.get("uploaded_at"),
        }
        for item in case.get("evidence", [])
    ]

    # Missing information / evidence
    missing_evidence = list(raw.get("unavailable_evidence", []))
    missing_evidence += [f"Item: {u}" for u in raw.get("unknown_evidence", [])]
    if domain_info.get("ambiguity"):
        missing_evidence += domain_info["ambiguity"][:3]

    clarification_questions = compact_clarification(case.get("clarification_rounds", []))
    issues = compact_issues(legal_issues_dict)

    # Specialist outputs
    specialist_outputs = []
    for sname, sdata in specialists_dict.items():
        if isinstance(sdata, dict):
            specialist_outputs.append({
                "specialist": sname,
                "agent": sdata.get("agent", sname),
                "domain": sdata.get("domain", ""),
                "observations": sdata.get("observations", []),
                "issue_families": sdata.get("issue_families", []),
            })

    # Legal authority findings & status resolution
    applicable_law = []
    authority_versions = {}
    unresolved_requirements = []
    legal_status = "NOT_REQUESTED"

    if foundation:
        if foundation.get("status") == "SOURCE_VERIFIED" and corpus is not None:
            # Genuine verified authority path
            laws = {}
            for iid in foundation.get("findings", {}):
                for app in data.get("legal_applications", {}).get(iid, {}).get("applications", []):
                    source = corpus.get(app["source_id"])
                    if source and source.get("version_id") == app.get("source_version"):
                        is_valid, _ = corpus.validate_source({k: v for k, v in source.items() if k != "version_id"})
                        if is_valid:
                            laws[app["source_id"]] = {
                                "provision_id": app["source_id"],
                                "title": source["title"],
                                "section": source.get("section"),
                                "citation": source.get("citation"),
                                "source_url": source.get("official_url"),
                                "retrieved_at": source.get("retrieved_at"),
                                "verification_status": "VERIFIED",
                                "authority_status": "VERIFIED_AUTHORITY",
                                "source_version": source["version_id"],
                                "explanation": "Official source checked and verified. Application requires advocate review.",
                            }
            if laws:
                applicable_law = list(laws.values())
                try:
                    authority_versions = authority_manifest(corpus, laws)
                    legal_status = "VERIFIED_AUTHORITY"
                except Exception:
                    legal_status = "PENDING_SOURCE"
                    unresolved_requirements.append("AUTHORITY_MANIFEST_REVALIDATION_REQUIRED")
            else:
                legal_status = "PENDING_SOURCE"
                unresolved_requirements.append("VERIFIED_SOURCE_COVERAGE_INCOMPLETE")
        else:
            # Legal foundation requested but unverified / pending / abstained
            # Inspect candidate retrieval decisions
            candidate_sources = []
            for iid in legal_issues_dict:
                citations = data.get("citation_verification." + iid, {}).get("decisions", [])
                for d in citations:
                    candidate_sources.append(d)

            if candidate_sources and any(d.get("status") == "PENDING" for d in candidate_sources):
                legal_status = "PENDING_SOURCE"
                unresolved_requirements.append("GENUINE_HUMAN_LEGAL_REVIEW_REQUIRED")
                unresolved_requirements.append("REVIEW_PENDING_CANDIDATE_CANNOT_ESTABLISH_LAW")
                # Expose candidate provisions with fail-closed PENDING status
                for d in candidate_sources:
                    sid = d.get("source_id")
                    if sid and sid not in {l.get("provision_id") for l in applicable_law}:
                        applicable_law.append({
                            "provision_id": sid,
                            "title": sid.replace("_", " ").title(),
                            "section": None,
                            "citation": None,
                            "source_url": None,
                            "retrieved_at": utc_now(),
                            "verification_status": "PENDING_HUMAN_REVIEW",
                            "authority_status": "PENDING_SOURCE",
                            "source_version": d.get("version_id"),
                            "explanation": "Official candidate source identified, but pending genuine Bar Council advocate review. Does NOT establish verified law.",
                        })
            elif any(d.get("status") in {"REJECTED", "NOT_APPLICABLE"} for d in candidate_sources):
                legal_status = "ABSTAINED"
                unresolved_requirements.append("NO_MATCHING_VERIFIED_AUTHORITY_COVERAGE")
            else:
                legal_status = "ABSTAINED"
                unresolved_requirements.append("CORPUS_COVERAGE_UNAVAILABLE_OR_ABSTAINED")
    elif case.get("legal_foundation_requested"):
        legal_status = "PENDING_SOURCE"
        unresolved_requirements.append("LEGAL_FOUNDATION_PIPELINE_IN_PROGRESS")
    else:
        legal_status = "NOT_REQUESTED"

    # Reconciliation / conflicts
    reconciliation_data = {
        "conflicts": [
            {
                "field": c.get("field"),
                "values": c.get("values"),
                "sources": c.get("sources"),
                "resolution": c.get("resolution"),
            }
            for c in board.get("conflicts", {}).values()
        ],
        "contested_claims": [f["proposition"] for f in disputed_facts],
    }

    # Summary and next steps
    narrative = case.get("client_story", "")
    normalized_narrative = (
        data.get("input", {}).get("canonical_narrative")
        or raw.get("canonical_narrative")
        or narrative
    )
    summary = build_citizen_summary(narrative, facts, domain_info)
    next_actions = build_safe_next_actions(legal_status, missing_evidence)

    # Versioning
    prior_file = case.get("case_file") or {}
    file_version = prior_file.get("version", 0) + 1
    input_version = case.get("input_version", 1)

    dependencies = versions(
        board,
        (
            "facts", "incidents", "timeline", "parties", "relationships",
            "evidence_mapping", "clarification", "reconciliation",
            "domain_classification", "agent_team", "legal_issues",
            "legal_foundation",
        ),
    )

    case_file = {
        "version": file_version,
        "case_file_version": file_version,
        "kind": "SOURCE_VERIFIED_ENGINE1" if legal_status == "VERIFIED_AUTHORITY" else "ENGINE1_CASE_FILE_V1",
        "created_at": utc_now(),
        "case_id": case_id,
        "original_narrative": narrative,
        "normalized_narrative": normalized_narrative,
        "intake": {"narrative": narrative},
        "facts": facts,
        "disputed_facts": disputed_facts,
        "timeline": timeline,
        "parties": parties,
        "relationships": relationships,
        "evidence_inventory": evidence_inventory,
        "evidence_mappings": evidence_mappings,
        "missing_evidence": missing_evidence,
        "missing_information": missing_evidence,
        "clarification_questions": clarification_questions,
        "issues": issues,
        "domains": domain_info,
        "specialist_outputs": specialist_outputs,
        "applicable_law": applicable_law,
        "legal_findings": applicable_law,
        "authority_provenance": authority_versions,
        "authority_versions": authority_versions,
        "legal_foundation_status": legal_status,
        "unresolved_legal_requirements": unresolved_requirements,
        "reconciliation": reconciliation_data,
        "citizen_safe_summary": summary,
        "next_actions": next_actions,
        "pipeline_status": case.get("status", "CASE_UNDERSTANDING_READY"),
        "stage_provenance": {
            "board_version": board.get("version", 1),
            "input_version": input_version,
            "dependency_versions": dependencies,
            "created_at": utc_now(),
        },
        "dependency_versions": dependencies,
        "foundation_complete": legal_status == "VERIFIED_AUTHORITY",
        "pending_advocate_verification": [
            {
                "type": "legal_verification",
                "reason": "Independent Bar Council-enrolled advocate review is required to verify applicable law.",
            }
        ] if legal_status != "VERIFIED_AUTHORITY" else [],
        "processing_mode": case.get("raw_package", {}).get("processing_mode") or "mock",
    }

    # Persist immutable snapshot to database
    snapshot_id = f"{case_id}:{file_version}"
    try:
        if not db.get("engine1_canonical_case_files", snapshot_id):
            db.create("engine1_canonical_case_files", {"id": snapshot_id, "case_id": case_id, "case_file": case_file})
    except Exception:
        pass

    # Update case record
    case_update = {
        "legal_case_file_current": legal_status == "VERIFIED_AUTHORITY",
        "canonical_case_file": case_file,
        "facts": facts,
        "timeline": timeline,
        "parties": parties,
        "legal_issues": issues,
    }
    if legal_status == "VERIFIED_AUTHORITY":
        case_update["case_file"] = case_file
    db.update("cases", case_id, case_update)

    return case_file
