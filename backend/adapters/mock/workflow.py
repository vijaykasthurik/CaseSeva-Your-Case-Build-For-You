from typing import Any
from uuid import uuid4

from ..database import DatabaseAdapter
from ..workflow import WorkflowAdapter


class MockWorkflowAdapter(WorkflowAdapter):
    processing_capability = "mock"
    def __init__(self, database: DatabaseAdapter):
        self.database = database

    def start_run(self, case_id: str, stages: list[str]) -> dict[str, Any]:
        run = {
            "id": uuid4().hex,
            "case_id": case_id,
            "stages": stages,
            "current_index": 0,
            "status": "running" if stages else "completed",
        }
        self.database.create("workflow_runs", run)
        return run

    def get_run_status(self, run_id: str) -> dict[str, Any] | None:
        return self.database.get("workflow_runs", run_id)

    def advance_run(self, run_id: str) -> dict[str, Any]:
        run = self.database.get("workflow_runs", run_id)
        if run is None:
            raise KeyError(run_id)
        next_index = run["current_index"] + 1
        changes = {
            "current_index": next_index,
            "status": "completed" if next_index >= len(run["stages"]) else "running",
        }
        updated_run = self.database.update("workflow_runs", run_id, changes)
        return updated_run
