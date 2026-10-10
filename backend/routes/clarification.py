from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Literal
from .dependencies import get_current_user, get_case_or_error
from .advocates import accepted_case
from ..models.case import utc_now
from ..services.blackboard import write
from ..services.jobs import dispatch

router = APIRouter(prefix="/api/cases")


class Answer(BaseModel):
    question_id: str
    response: Literal["ANSWER", "UNKNOWN", "NOT_AVAILABLE", "LATER"]
    value: str = ""
    evidence_ids: list[str] = Field(default_factory=list)


class Answers(BaseModel):
    answers: list[Answer]


@router.post("/{case_id}/clarifications")
def answer(case_id: str, body: Answers, request: Request, user=Depends(get_current_user)):
    case = accepted_case(request, case_id, user) if user.get("role") == "advocate" else get_case_or_error(request, case_id, user)
    rounds = case.get("clarification_rounds", [])
    if not rounds or rounds[-1]["status"] != "WAITING" or case["status"] != "AWAITING_CLIENT_INFO":
        raise HTTPException(409, "No unanswered clarification batch is waiting.")
    batch = rounds[-1]
    if batch["answering_user_id"] != user["id"]:
        raise HTTPException(403, "These questions belong to the person who requested the analysis.")
    questions = {q["question_id"]: q for q in batch["questions"]}
    ids = [a.question_id for a in body.answers]
    if len(ids) != len(set(ids)) or set(ids) != set(questions):
        raise HTTPException(422, "Respond to every question. Unknown, not available and later are valid responses.")
    evidence = {item["evidence_id"] for item in case.get("evidence", [])}
    for item in body.answers:
        q = questions[item.question_id]
        if not set(item.evidence_ids).issubset(evidence): raise HTTPException(422, "Unknown evidence reference.")
        if item.response == "ANSWER":
            if q["control"] == "upload" and not item.evidence_ids: raise HTTPException(422, "Upload or select evidence, or choose an unavailable response.")
            if q["control"] != "upload" and not item.value.strip(): raise HTTPException(422, "An answer cannot be empty. You may choose 'I don't know'.")
            if q["control"] == "single_choice" and item.value not in q["choices"]: raise HTTPException(422, "Choose one of the offered answers.")
            if q["control"] in {"date", "month"}:
                from datetime import datetime
                import re
                pattern, format = (r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d") if q["control"] == "date" else (r"\d{4}-\d{2}", "%Y-%m")
                try:
                    if not re.fullmatch(pattern, item.value): raise ValueError()
                    datetime.strptime(item.value, format)
                except ValueError:
                    raise HTTPException(422, "Use a valid date/month, or choose an unknown response.")
    batch.update({"answers": [item.model_dump() for item in body.answers], "status": "ANSWERED", "answered_at": utc_now(), "answered_by": user["id"]})
    write(request.app.state.adapters.database, case_id, {"clarification_rounds": rounds, "status": "ENGINE1_RUNNING", "input_version": case.get("input_version", 1) + 1, "engine2_stale": bool(case.get("engine2")), "documents_outdated": bool(case.get("document_version"))}, user["id"], "clarification_answered")
    try: dispatch(request.app, 1, case_id, start_stage=batch["resume_stage"])
    except Exception:
        write(request.app.state.adapters.database, case_id, {"status": "REVIEW_REQUIRED", "processing_error": {"engine": 1, "message": "Your answers are saved, but processing could not resume. Please retry."}}, action="resume_failed")
        raise HTTPException(503, "Your answers are saved. Processing needs to be resumed.")
    return {"status": "resuming"}
