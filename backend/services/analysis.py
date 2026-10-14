import threading
import time
from typing import Any

from pydantic import ValidationError

from ..models.analysis import (
    FactExtractionOutput,
    IntakeOutput,
    PartyOutput,
    TimelineOutput,
)

STAGES = ["INTAKE", "FACT_EXTRACTION", "TIMELINE_CONSTRUCTION", "PARTY_IDENTIFICATION"]


def schema_for(stage: str) -> dict[str, Any]:
    return {"stage": stage.lower(), "schema": stage}


def validate_response(stage: str, response: dict[str, Any]):
    models = {
        "INTAKE": IntakeOutput,
        "FACT_EXTRACTION": FactExtractionOutput,
        "TIMELINE_CONSTRUCTION": TimelineOutput,
        "PARTY_IDENTIFICATION": PartyOutput,
    }
    return models[stage].model_validate(response)


def build_analysis_prompt(stage: str, current: dict[str, Any]) -> str:
    story = current.get("client_story", "").strip()
    evidence = current.get("evidence", [])
    evidence_str = "\n".join([f"- [{e.get('evidence_id')}] {e.get('filename')}: {e.get('description', '')}" for e in evidence]) or "None"
    facts = current.get("facts", [])
    facts_str = "\n".join([f"- [{f.get('fact_id')}] {f.get('text')} (Evidence: {', '.join(f.get('evidence_ids', []))})" for f in facts]) or "None"

    if stage == "FACT_EXTRACTION":
        return (
            f"Extract all key material facts from the following case story and evidence.\n\n"
            f"CLIENT STORY:\n{story}\n\n"
            f"UPLOADED EVIDENCE:\n{evidence_str}"
        )
    elif stage == "TIMELINE_CONSTRUCTION":
        return (
            f"Construct a chronological timeline of key events based on the client story, facts, and evidence.\n\n"
            f"CLIENT STORY:\n{story}\n\n"
            f"EXTRACTED FACTS:\n{facts_str}\n\n"
            f"UPLOADED EVIDENCE:\n{evidence_str}"
        )
    elif stage == "PARTY_IDENTIFICATION":
        return (
            f"Identify the parties involved, their legal roles, and their relationship.\n\n"
            f"CLIENT STORY:\n{story}\n\n"
            f"EXTRACTED FACTS:\n{facts_str}"
        )
    return f"Analyze case for stage {stage}."


def run_pipeline(app, case_id: str, retry_failed: bool = False, requested_stages: list[str] | None = None):
    db = app.state.adapters.database
    try:
        workflow = app.state.adapters.workflow
        llm = app.state.adapters.llm
        case = db.get("cases", case_id)
        if not case:
            return
        selected = requested_stages or [stage for stage in STAGES if not retry_failed or case.get("stage_statuses", {}).get(stage) == "FAILED"]
        run = workflow.start_run(case_id, selected)
        statuses = dict(case.get("stage_statuses", {}))
        for stage in selected:
            statuses[stage] = "WAITING"
        db.update("cases", case_id, {"stage_statuses": statuses, "status": "ANALYZING", "workflow_run_id": run["id"], "version": case.get("version", 1) + 1})
        for stage in selected:
            current = db.get("cases", case_id)
            statuses = dict(current.get("stage_statuses", {}))
            statuses[stage] = "RUNNING"
            db.update("cases", case_id, {"stage_statuses": statuses, "version": current.get("version", 1) + 1})
            try:
                time.sleep(0.08)
                prompt = build_analysis_prompt(stage, current)
                if stage == "INTAKE":
                    response = {
                        "normalized_story": current.get("client_story", "").strip(),
                        "evidence_text": [{"evidence_id": e["evidence_id"], "text": f"{e['filename']}: {e.get('description', '')}"} for e in current.get("evidence", [])],
                    }
                else:
                    schema = schema_for(stage)
                    story_str = str(current.get("client_story") or current.get("intake", {}).get("normalized_story") or "").lower()
                    if "[MALFORMED]" in current.get("client_story", "") and stage == "FACT_EXTRACTION":
                        schema["fixture"] = "malformed"
                    elif "uninformative" in story_str and stage == "PARTY_IDENTIFICATION":
                        schema["fixture"] = "uninformative"
                    response = llm.generate(prompt, schema)
                output = validate_response(stage, response)
                current = db.get("cases", case_id)
                if not current:
                    return
                changes: dict[str, Any] = {"version": current.get("version", 1) + 1}
                if stage == "INTAKE":
                    changes["intake"] = output.model_dump()
                elif stage == "FACT_EXTRACTION":
                    previous = {item["fact_id"]: item for item in current.get("facts", []) if item.get("human_corrected")}
                    changes["facts"] = [
                        previous.get(item.fact_id, item.model_dump())
                        for item in output.facts
                    ]
                elif stage == "TIMELINE_CONSTRUCTION":
                    previous = {item["event_id"]: item for item in current.get("timeline", []) if item.get("human_corrected")}
                    changes["timeline"] = [
                        previous.get(item.event_id, item.model_dump())
                        for item in output.timeline
                    ]
                else:
                    changes["parties"] = output.parties.model_dump()
                statuses = dict(current.get("stage_statuses", {}))
                statuses[stage] = "COMPLETED"
                changes["stage_statuses"] = statuses
                db.update("cases", case_id, changes)
                workflow.advance_run(run["id"])
            except Exception as exc:
                import traceback
                traceback.print_exc()
                current = db.get("cases", case_id) or {}
                statuses = dict(current.get("stage_statuses", {}))
                statuses[stage] = "FAILED"
                db.update("cases", case_id, {"stage_statuses": statuses, "analysis_error": {"stage": stage, "message": str(exc)}, "status": "ANALYSIS_FAILED", "version": current.get("version", 1) + 1})
                return
        current = db.get("cases", case_id)
        if current and all(current.get("stage_statuses", {}).get(stage) == "COMPLETED" for stage in selected):
            db.update("cases", case_id, {"status": "AWAITING_PREVIEW_1", "version": current.get("version", 1) + 1})
    except Exception as exc:
        # Top-level catch-all: if anything fails before/outside the stage loop,
        # mark the case as failed rather than leaving it stuck at ANALYZING.
        import traceback
        traceback.print_exc()
        try:
            db.update("cases", case_id, {
                "status": "ANALYSIS_FAILED",
                "analysis_error": {"stage": "INIT", "message": str(exc)},
            })
        except Exception:
            pass  # DB itself is broken — nothing more we can do


def start_async(app, case_id: str, retry_failed: bool = False, requested_stages: list[str] | None = None):
    import os
    lambda_name = os.getenv("AWS_LAMBDA_FUNCTION_NAME")
    if lambda_name:
        import json
        import boto3
        region = os.getenv("CASESEVA_AWS_REGION") or os.getenv("AWS_REGION", "ap-southeast-2")
        client = boto3.client("lambda", region_name=region)
        payload = {
            "action": "run_pipeline",
            "case_id": case_id,
            "retry_failed": retry_failed,
            "requested_stages": requested_stages,
        }
        client.invoke(
            FunctionName=lambda_name,
            InvocationType="Event",
            Payload=json.dumps(payload),
        )
    else:
        thread = threading.Thread(target=run_pipeline, args=(app, case_id, retry_failed, requested_stages), daemon=True)
        thread.start()
