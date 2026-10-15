"""Engine 2: Strengthen My Case — Challenge Analysis and Adversarial Preparation.

Product Principle:
"We don’t ask AI to predict whether the citizen will win.
We ask AI to discover why the case could lose before an advocate uses it."

Core Properties:
- Consumes immutable engine1_canonical_case_files snapshot
- Binds permanently to (case_id, engine1_case_file_version)
- Operates safely across all legal_foundation_status states (VERIFIED_AUTHORITY, PENDING_SOURCE, ABSTAINED, etc.)
- Never asserts or manufactures statutory provisions when legal foundation is unverified
- REVIEW_PENDING candidates never become verified law
- Strict reference validation: only verified facts, evidence, and provisions can be cited
- No outcome prediction, no win probability, no victory percentages
- Immutable append-only persistence in engine2_challenge_reports
- Output isolated from Engine 1; Engine 1 case file remains immutable
"""
from __future__ import annotations

import copy
import json
from typing import Any, Optional
from uuid import uuid4

from ..adapters.capabilities import processing_mode
from ..models.case import utc_now
from ..models.engines import (
    ENGINE2_STAGES,
    CaseChallengeReport,
    Counsel,
    Opponent,
    OpposingArgument,
    Replies,
    Evaluation,
    FactualWeakness,
    EvidenceGap,
    Contradiction,
    ProceduralRisk,
    AlternativeInterpretation,
    IssueChallenge,
)
from ..models.legal import ChallengerOutput
from .blackboard import engine_state, write


def get_canonical_foundation(case: dict[str, Any], db: Any) -> tuple[dict[str, Any], int]:
    """Retrieves the authoritative canonical case file snapshot and its exact version."""
    # 1. Prefer case['canonical_case_file'] if present
    file = case.get("canonical_case_file")
    if file and isinstance(file, dict) and file.get("version"):
        return copy.deepcopy(file), file["version"]

    # 2. Query engine1_canonical_case_files collection
    try:
        snapshots = db.list("engine1_canonical_case_files")
        case_snapshots = [
            s.get("case_file") for s in snapshots
            if s.get("case_id") == case.get("case_id") and s.get("case_file")
        ]
        if case_snapshots:
            case_snapshots.sort(key=lambda s: s.get("version", 0))
            latest = case_snapshots[-1]
            return copy.deepcopy(latest), latest["version"]
    except Exception:
        pass

    # 3. Fallback to legacy case['case_file']
    if case.get("case_file") and isinstance(case["case_file"], dict) and case["case_file"].get("version"):
        legacy = case["case_file"]
        return copy.deepcopy(legacy), legacy["version"]

    raise ValueError("A canonical Engine-1 Case File snapshot is required to run Strengthen My Case.")


def validate_references(output: Any, case_file: dict[str, Any]) -> None:
    """Validates that argument references point only to verified facts, evidence, and authorities."""
    valid_facts = {
        item["fact_id"] for item in case_file.get("facts", [])
        if not item.get("removed") and (
            item.get("verification_status") == "VERIFIED"
            or item.get("source_status") == "SUPPORTED_BY_EVIDENCE"
            or item.get("advocate_approved")
        )
    }

    evidence_items = case_file.get("evidence_inventory") or case_file.get("evidence_index") or []
    valid_evidence = {
        item["evidence_id"] for item in evidence_items
        if not item.get("removed") and (
            item.get("verification_status") == "VERIFIED"
            or item.get("advocate_approved")
            or item.get("readable") is True
        )
    }

    # Only verified statutory provisions are eligible.
    # If legal foundation is PENDING_SOURCE or ABSTAINED, this set is strictly empty.
    applicable_law = case_file.get("applicable_law", [])
    valid_provisions = {
        item["provision_id"] for item in applicable_law
        if not item.get("removed") and (
            item.get("verification_status") == "VERIFIED"
            or item.get("authority_status") == "VERIFIED_AUTHORITY"
        )
    }

    ids = {
        "fact_ids": valid_facts,
        "evidence_ids": valid_evidence,
        "provision_ids": valid_provisions,
    }

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ids and not set(child).issubset(ids[key]):
                    raise ValueError(f"Argument output contains unknown or unverified {key}.")
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(output)


def sanitize_argument_references(output: Any, case_file: dict[str, Any]) -> None:
    """Sanitizes argument references so unverified facts or provisions are omitted from premises."""
    valid_facts = {
        item["fact_id"] for item in case_file.get("facts", [])
        if not item.get("removed") and (
            item.get("verification_status") == "VERIFIED"
            or item.get("source_status") == "SUPPORTED_BY_EVIDENCE"
            or item.get("advocate_approved")
        )
    }
    evidence_items = case_file.get("evidence_inventory") or case_file.get("evidence_index") or []
    valid_evidence = {
        item["evidence_id"] for item in evidence_items
        if not item.get("removed") and (
            item.get("verification_status") == "VERIFIED"
            or item.get("advocate_approved")
            or item.get("readable") is True
        )
    }
    applicable_law = case_file.get("applicable_law", [])
    valid_provisions = {
        item["provision_id"] for item in applicable_law
        if not item.get("removed") and (
            item.get("verification_status") == "VERIFIED"
            or item.get("authority_status") == "VERIFIED_AUTHORITY"
        )
    }
    allowed = {
        "fact_ids": valid_facts,
        "evidence_ids": valid_evidence,
        "provision_ids": valid_provisions,
    }
    def walk_clean(val: Any) -> None:
        if isinstance(val, dict):
            for k in ("fact_ids", "evidence_ids", "provision_ids"):
                if k in val and isinstance(val[k], list):
                    val[k] = [x for x in val[k] if x in allowed[k]]
            for child in val.values():
                walk_clean(child)
        elif isinstance(val, list):
            for child in val:
                walk_clean(child)
    walk_clean(output)


def run_engine2(
    app: Any,
    case_id: str,
    start_stage: Optional[str] = None,
    actor_id: Optional[str] = None,
    actor_role: str = "citizen",
) -> None:
    """Executes Engine 2 (Strengthen My Case) against the canonical Case File snapshot."""
    adapters = app.state.adapters
    db = adapters.database
    case = db.get("cases", case_id)
    if not case:
        raise ValueError(f"Case '{case_id}' does not exist.")

    # Ingest canonical snapshot
    foundation, foundation_version = get_canonical_foundation(case, db)
    actor_id = actor_id or case.get("engine2_requested_by") or case.get("owner_user_id") or "citizen_user"

    legal_status = foundation.get("legal_foundation_status", "NOT_REQUESTED")
    legal_limitations: list[str] = []
    if legal_status != "VERIFIED_AUTHORITY":
        legal_limitations.append(
            f"Legal foundation status is {legal_status}. Statutory authorities were not asserted or treated as verified law."
        )
        legal_limitations.append(
            "Factual disputes, evidence vulnerabilities, and procedural risks were evaluated without asserting statutory citations."
        )
        # Ensure applicable_law in context is strictly empty to fail closed
        foundation["applicable_law"] = []

    stages = ENGINE2_STAGES
    if start_stage:
        stages = stages[stages.index(start_stage):]
    statuses = {name: "WAITING" for name in stages}
    db.update("cases", case_id, {
        "status": "ENGINE2_RUNNING",
        "active_engine": "Engine 2 — Challenge + Strengthen",
        "stage_statuses": statuses,
        "processing_error": None,
        "engine2_choice": "RUN",
    })
    result = copy.deepcopy(case.get("engine2", {}))
    engine_state(db, case_id, 2, "RUNNING", case_file_version=foundation_version)

    try:
        # Determine target issues from Phase-5 CASE_ISSUES or legal_issues
        target_issues_list = foundation.get("issues") or foundation.get("legal_issues") or foundation.get("case_issues") or []
        target_issue_ids = {
            item.get("issue_id") or item.get("question_id")
            for item in target_issues_list
            if item.get("issue_id") or item.get("question_id")
        }

        for stage in stages:
            statuses[stage] = "RUNNING"
            db.update("cases", case_id, {"stage_statuses": dict(statuses), "current_stage": stage})

            if stage == "OVERVIEW_BUILDER":
                result["overview_ready"] = True
            else:
                models = {
                    "CLAIMANT_COUNSEL": Counsel,
                    "OPPONENT_COUNSEL": Opponent,
                    "EVIDENCE_CHALLENGER": ChallengerOutput,
                    "REBUTTAL": Replies,
                    "NEUTRAL_EVALUATION": Evaluation,
                }
                model = models[stage]
                context = {
                    "case_file": foundation,
                    "argument_results": result,
                    "professional_overrides": case.get("professional_overrides", []),
                }
                prompt = (
                    "You perform only challenge and strengthening analysis on the supplied versioned Case File. "
                    "Discover why the case could lose before an advocate uses it. "
                    "Never re-extract facts, route domains, retrieve or verify law, or calculate forum/limitation. "
                    "Do not predict whether the citizen will win. No win probability, victory percentage, or overall strength score. "
                    "Use only applicable_law records marked VERIFIED as authority. If applicable_law is empty, create no statutory authority. "
                    "References belong in structured provision_ids, not invented citations in prose. "
                    "Argument fact_ids may reference only VERIFIED or supported facts. "
                    "For NEUTRAL_EVALUATION rate each issue for preparation readiness, not victory likelihood. "
                    "Be focused and concise. Provide 2-5 high-impact items per category without redundant repetition. "
                    "Return JSON matching " + json.dumps(model.model_json_schema()) + "\nDATA:\n" + json.dumps(context, ensure_ascii=False)
                )

                output = model.model_validate(
                    adapters.llm.generate(
                        prompt,
                        {
                            "stage": "engine2_" + stage.lower(),
                            "json_schema": model.model_json_schema(),
                            "workflow_version": 2,
                            "max_tokens": 8000,
                            "development_context": context,
                        },
                    )
                ).model_dump()

                sanitize_argument_references(output, foundation)
                validate_references(output, foundation)

                if stage == "OPPONENT_COUNSEL":
                    for entry in case.get("professional_overrides", []):
                        if entry.get("target", "").startswith("argument:"):
                            identifier = entry["target"].split(":", 1)[1]
                            output["objections"] = [
                                item for item in output.get("objections", [])
                                if item.get("objection_id") != identifier
                            ] + [entry.get("new")]
                    sanitize_argument_references(output, foundation)
                    validate_references(output, foundation)

                if stage == "NEUTRAL_EVALUATION":
                    issues = [item["issue_id"] for item in output.get("issue_readiness", [])]
                    if target_issue_ids:
                        if len(issues) != len(set(issues)) or set(issues) != target_issue_ids:
                            # If mock or LLM returned a mismatch, align to target_issues exactly once
                            aligned_readiness = []
                            for tid in sorted(target_issue_ids):
                                existing = next((it for it in output.get("issue_readiness", []) if it["issue_id"] == tid), None)
                                if existing:
                                    aligned_readiness.append(existing)
                                else:
                                    aligned_readiness.append({
                                        "issue_id": tid,
                                        "level": "Unresolved",
                                        "reasons": ["Factual review indicated."],
                                        "evidence_ids": [],
                                        "provision_ids": [],
                                        "improvements": ["Provide supporting documents."],
                                    })
                            output["issue_readiness"] = aligned_readiness

                result[stage.lower()] = output

                if stage == "EVIDENCE_CHALLENGER" and any(not item.get("resolved") for item in output.get("document_requests", [])):
                    # Note: we complete all stages to produce the challenge report rather than halting early,
                    # but record requested documents.
                    pass

            statuses[stage] = "COMPLETED"
            db.update("cases", case_id, {"stage_statuses": dict(statuses)})

        # Verify that Case File was not mutated during execution
        current_foundation, current_version = get_canonical_foundation(db.get("cases", case_id), db)
        if current_version != foundation_version:
            raise ValueError("The Case File changed during argument analysis; rerun Engine 2.")

        # Determine version counter from existing challenge reports
        existing_reports = [
            r for r in db.list("engine2_challenge_reports")
            if r.get("case_id") == case_id
        ]
        run_version = len(existing_reports) + 1
        run_id = uuid4().hex

        # Construct challenge perspectives
        challenge_perspectives = [
            "OPPOSING_PARTY",
            "EVIDENCE_CHALLENGE",
            "CHRONOLOGY_AND_DELAY",
            "FACTUAL_CONTRADICTIONS",
            "PROCEDURAL_RISK",
        ]

        # Extract opposing arguments
        opposing_arguments = []
        for obj in result.get("opponent_counsel", {}).get("objections", []):
            opposing_arguments.append(OpposingArgument(
                argument_id=obj.get("objection_id", uuid4().hex[:8]),
                perspective="OPPOSING_PARTY",
                title=obj.get("text", "")[:60],
                summary=obj.get("text", ""),
                target_facts=obj.get("fact_ids", []),
                target_evidence=obj.get("evidence_ids", []),
                counter_propositions=[obj.get("text", "")],
                provision_ids=obj.get("provision_ids", []),
            ))

        # Extract factual weaknesses
        factual_weaknesses = []
        for fact in foundation.get("facts", []):
            if fact.get("source_status") == "UNVERIFIED":
                factual_weaknesses.append(FactualWeakness(
                    weakness_id=f"fw_{fact.get('fact_id', uuid4().hex[:6])}",
                    description=f"Fact '{fact.get('text', '')[:80]}' is unverified and stated only without documentation.",
                    fact_ids=[fact.get("fact_id")],
                    severity="MEDIUM",
                    clarification_suggested="Provide contemporaneous evidence or invoice.",
                ))
        for attack in result.get("evidence_challenger", {}).get("attacks", []):
            if attack:
                factual_weaknesses.append(FactualWeakness(
                    weakness_id=f"fw_{uuid4().hex[:8]}",
                    description=str(attack),
                    severity="HIGH",
                ))

        # Extract evidence gaps
        evidence_gaps = []
        for req in result.get("evidence_challenger", {}).get("document_requests", []):
            evidence_gaps.append(EvidenceGap(
                gap_id=req.get("request_id", uuid4().hex[:8]),
                description=req.get("description", "Missing documentation"),
                suggested_evidence=[req.get("description", "")],
            ))
        for missing in foundation.get("missing_evidence", []):
            if isinstance(missing, str) and missing:
                evidence_gaps.append(EvidenceGap(
                    gap_id=f"gap_{uuid4().hex[:8]}",
                    description=missing,
                    suggested_evidence=[missing],
                ))

        # Extract contradictions
        contradictions = []
        reconciliation_conflicts = foundation.get("reconciliation", {}).get("conflicts", [])
        for conf in reconciliation_conflicts:
            if isinstance(conf, dict) and conf.get("field"):
                contradictions.append(Contradiction(
                    contradiction_id=f"contra_{uuid4().hex[:8]}",
                    description=f"Contradiction regarding {conf.get('field')}: values {conf.get('values')}",
                    conflicting_statements=[str(v) for v in conf.get("values", [])],
                    resolution_path=conf.get("resolution"),
                ))

        # Extract procedural risks
        procedural_risks = []
        for risk in result.get("neutral_evaluation", {}).get("unresolved_risks", []):
            if risk:
                procedural_risks.append(ProceduralRisk(
                    risk_id=f"pr_{uuid4().hex[:8]}",
                    category="GENERAL",
                    description=str(risk),
                ))

        # Issue-by-issue challenges
        issue_challenges = []
        eval_readiness = {
            item["issue_id"]: item
            for item in result.get("neutral_evaluation", {}).get("issue_readiness", [])
        }
        for item in target_issues_list:
            iid = item.get("issue_id") or item.get("question_id")
            if not iid:
                continue
            readiness_meta = eval_readiness.get(iid, {})
            readiness_level = readiness_meta.get("level", "Partially supported")
            if readiness_level not in {"Well supported", "Partially supported", "Thin", "Unresolved"}:
                readiness_level = "Partially supported"

            issue_challenges.append(IssueChallenge(
                issue_id=iid,
                question=item.get("question") or item.get("text") or "Factual dispute",
                category=item.get("category", "FACTUAL_DISPUTE"),
                readiness=readiness_level,
                opposing_argument=(readiness_meta.get("reasons") or ["Opposing stance requires rebuttal."])[0],
                supporting_facts=[f.get("fact_id") for f in foundation.get("facts", []) if f.get("source_status") == "SUPPORTED_BY_EVIDENCE"],
                weakening_facts=[f.get("fact_id") for f in foundation.get("facts", []) if f.get("source_status") == "UNVERIFIED"],
                evidence_supporting=readiness_meta.get("evidence_ids", []),
                evidence_missing=[g.description for g in evidence_gaps[:2]],
                contradictions=[c.description for c in contradictions[:1]],
                assumptions=["Citizen assumes good faith and seller responsibility."],
                preparation_needs=readiness_meta.get("improvements", ["Assemble proof of transaction and notice."]),
            ))

        # Questions and preparation actions
        questions = list(result.get("neutral_evaluation", {}).get("advocate_review_points", []))
        if not questions:
            questions = [
                "Can you produce contemporaneous proof of purchase or repair refusal?",
                "Was written notice served on the opposite party prior to approaching formal dispute forums?",
            ]

        preparation_actions = [
            "Gather all invoices, delivery notes, and communication logs in chronological order.",
            "Identify whether any timeline dates are estimates and confirm exact calendar dates.",
            "Draft a clear timeline summary highlighting when defects were first brought to notice.",
        ]

        # Alternative interpretations
        alternative_interpretations = [
            AlternativeInterpretation(
                interpretation_id=f"ai_{uuid4().hex[:8]}",
                description="Opposing party may contend delay in reporting or user-induced damage.",
                competing_narrative="The seller or service provider may claim the goods were delivered intact and deterioration occurred subsequent to receipt.",
                vulnerable_claims=[f.get("proposition", "") for f in foundation.get("disputed_facts", [])][:2],
            )
        ]

        # Assemble canonical report
        challenge_report = CaseChallengeReport(
            engine2_run_id=run_id,
            case_id=case_id,
            engine1_case_file_version=foundation_version,
            requested_by_actor_id=actor_id,
            requested_by_role=actor_role,
            created_at=utc_now(),
            version=run_version,
            status="COMPLETED",
            challenge_perspectives=challenge_perspectives,
            opposing_arguments=opposing_arguments,
            factual_weaknesses=factual_weaknesses,
            evidence_gaps=evidence_gaps,
            contradictions=contradictions,
            procedural_risks=procedural_risks,
            alternative_interpretations=alternative_interpretations,
            unresolved_assumptions=[
                "Assumes manufacturer/seller warranty conditions were satisfied.",
                "Assumes notice was received by an authorized representative.",
            ],
            legal_authority_limitations=legal_limitations,
            questions_for_citizen_or_advocate=questions,
            preparation_actions=preparation_actions,
            issue_challenges=issue_challenges,
            provenance={
                "engine1_case_file_version": foundation_version,
                "legal_foundation_status": legal_status,
                "processing_mode": processing_mode(adapters),
                "created_at": utc_now(),
            },
        )

        # 6. Immutable persistence in engine2_challenge_reports
        db.create("engine2_challenge_reports", {
            "id": run_id,
            "engine2_run_id": run_id,
            "case_id": case_id,
            "engine1_case_file_version": foundation_version,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "created_at": challenge_report.created_at,
            "version": run_version,
            "status": challenge_report.status,
            "report": challenge_report.model_dump(),
        })

        # Backward compatibility for engine2_versions collection
        db.create("engine2_versions", {
            "id": uuid4().hex,
            "case_id": case_id,
            "output": challenge_report.to_legacy_dict(),
        })

        # Update case record without mutating Engine 1 Case File
        legacy_output = challenge_report.to_legacy_dict()
        changes = {
            "engine2": legacy_output,
            "engine2_report": challenge_report.model_dump(),
            "engine2_stale": False,
            "engine2_case_file_version": foundation_version,
            "status": "ENGINE2_DONE",
            "current_stage": None,
            "documents_outdated": bool(case.get("document_version")),
        }
        if case.get("assigned_advocate_id"):
            changes["status"] = "ADVOCATE_REVIEW"

        write(db, case_id, changes, action="engine2_completed")
        engine_state(db, case_id, 2, "COMPLETE", version=run_version, case_file_version=foundation_version)

        from .notifications import notify
        notify(db, case.get("owner_user_id", ""), "Your deeper case-checking overview is ready.", case_id, "CHALLENGE_FINISHED")

    except Exception as exc:
        stage = next((name for name, value in statuses.items() if value == "RUNNING"), "ENGINE2_VALIDATION")
        statuses[stage] = "FAILED"
        db.update("cases", case_id, {
            "status": "REVIEW_REQUIRED",
            "stage_statuses": statuses,
            "processing_error": {"engine": 2, "stage": stage, "message": str(exc)},
            "current_stage": None,
        })
        engine_state(db, case_id, 2, "FAILED", resume_stage=stage)
