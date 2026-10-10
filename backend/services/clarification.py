from ..models.case import utc_now
from .blackboard import engine_state, write


def gate(db, case, data, questions, resume_stage):
    rounds = case.get("clarification_rounds", [])
    answered = {q["question_id"] for batch in rounds for q in batch.get("questions", [])}
    questions = [q for q in questions if q["question_id"] not in answered]
    if not questions: return False
    if len(rounds) >= 2:
        data.setdefault("advocate_flags", []).append({"type": "clarification_limit", "reason": "Important details remain unknown after two question rounds.", "questions": questions})
        return False
    ids = [q["question_id"] for q in questions]
    if len(ids) != len(set(ids)): raise ValueError("Clarification question IDs must be unique.")
    incidents = {item["incident_id"] for item in data.get("incidents", [])}
    if any(q["incident_id"] not in incidents for q in questions):
        raise ValueError("Clarification questions must belong to an extracted incident.")
    actor = case.get("analysis_requested_by") or case.get("created_by_advocate_id") or case["owner_user_id"]
    batch = {"round": len(rounds) + 1, "questions": questions, "answers": [], "status": "WAITING", "answering_user_id": actor, "resume_stage": resume_stage, "created_at": utc_now()}
    write(db, case["case_id"], {"status": "AWAITING_CLIENT_INFO", "journey_stage": "AWAITING_CLIENT_INFO", "clarification_rounds": rounds + [batch], "engine1_checkpoint": data, "current_stage": None}, action="clarification_requested")
    engine_state(db, case["case_id"], 1, "WAITING_FOR_INPUT")
    return True
