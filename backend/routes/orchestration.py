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
    try:
        registry = production_registry(request.app.state.adapters)
        if case.get('legal_foundation_requested'):
            from ..services.case_blackboard import CaseBlackboard
            from ..services.legal_registry import legal_registry
            from ..services.verified_corpus import VerifiedCorpus
            registry, _ = legal_registry(request.app.state.adapters, VerifiedCorpus(db), CaseBlackboard(db).read_board(case_id))
        controller = MasterLegalOrchestrator(db, registry)
        controller.store.sync_input(case_id)
        return controller.diagnostics(case_id)
    except Exception:
        raise HTTPException(503, "Orchestration diagnostics are temporarily unavailable.")
