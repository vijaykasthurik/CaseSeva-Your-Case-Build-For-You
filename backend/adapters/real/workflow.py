from typing import Any

from ..workflow import WorkflowAdapter


class RealWorkflowAdapter(WorkflowAdapter):
    processing_capability = "unavailable"
    def start_run(self, case_id: str, stages: list[str]) -> dict[str, Any]:
        # TODO: AWS
        raise NotImplementedError

    def get_run_status(self, run_id: str) -> dict[str, Any] | None:
        # TODO: AWS
        raise NotImplementedError

    def advance_run(self, run_id: str) -> dict[str, Any]:
        # TODO: AWS
        raise NotImplementedError
