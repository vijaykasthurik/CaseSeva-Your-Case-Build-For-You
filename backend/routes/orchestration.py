"""Read-only administrator diagnostics; no citizen/advocate execution backdoor."""
from fastapi import APIRouter, Depends, HTTPException, Request
from .dependencies import get_current_user
from .advocates import require_admin
from ..services.agent_registry import production_registry
from ..services.orchestrator import MasterLegalOrchestrator

router = APIRouter(prefix="/api/admin/cases")


@router.get("/{case_id}/orchestration")
def diagnostics(case_id: str, request: Request, user=Depends(get_current_user)):
    require_admin(request, user)
    db = request.app.state.adapters.database
    case = db.get("cases", case_id)
    if not case or case.get("status") == "DELETED":
        raise HTTPException(404, "Case not found")
    controller = MasterLegalOrchestrator(db, production_registry())
    try:
        controller.store.sync_input(case_id)
        return controller.diagnostics(case_id)
    except Exception:
        raise HTTPException(503, "Orchestration diagnostics are temporarily unavailable.")
