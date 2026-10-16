from fastapi import APIRouter, Request

router = APIRouter(prefix="/api")


@router.get("/health")
def health(request: Request) -> dict:
    adapters = request.app.state.adapters
    return {
        "status": "ok",
        "adapter_mode": adapters.mode,
        "providers": adapters.providers,
        "processing_mode": adapters.processing_mode,
        "capabilities": {
            "llm": adapters.llm_processing_mode,
            "workflow": adapters.workflow_processing_mode,
        },
        "media_capabilities": getattr(adapters, "media_capabilities", {}),
        "email_provider": adapters.email_provider,
    }


@router.get("/health/live")
def liveness() -> dict:
    return {"status": "alive"}


@router.get("/health/ready")
def readiness(request: Request) -> dict:
    adapters = getattr(request.app.state, "adapters", None)
    if not adapters:
        return {"status": "unavailable", "reason": "Adapters not loaded"}

    # 1. Database availability check
    db_ready = False
    try:
        # Ping or lightweight read without exposing data
        adapters.database.get("users", "healthcheck")
        db_ready = True
    except Exception:
        db_ready = False

    # 2. Storage availability check
    storage_ready = False
    try:
        if hasattr(adapters.storage, "list"):
            adapters.storage.list("")
            storage_ready = True
        else:
            storage_ready = True
    except Exception:
        storage_ready = False

    # 3. Model provider readiness
    llm_capability = getattr(adapters, "llm_processing_mode", "unavailable")
    llm_ready = llm_capability in {"mock", "live", "hybrid"}

    is_ready = db_ready and storage_ready

    return {
        "status": "ready" if is_ready else "degraded",
        "database": {"status": "ready" if db_ready else "unavailable", "provider": adapters.persistence_provider},
        "storage": {"status": "ready" if storage_ready else "unavailable", "provider": adapters.object_store_provider},
        "model_provider": {"status": "ready" if llm_ready else "unavailable", "capability": llm_capability},
    }
