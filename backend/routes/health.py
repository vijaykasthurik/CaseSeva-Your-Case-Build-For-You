from fastapi import APIRouter, Request

router = APIRouter(prefix="/api")


@router.get("/health")
def health(request: Request) -> dict:
    adapters = request.app.state.adapters
    return {"status": "ok", "adapter_mode": adapters.mode,
            "providers": adapters.providers, "processing_mode": adapters.processing_mode,
            "capabilities": {"llm": adapters.llm_processing_mode, "workflow": adapters.workflow_processing_mode},
            "media_capabilities": getattr(adapters, "media_capabilities", {}),
            "email_provider": adapters.email_provider}
