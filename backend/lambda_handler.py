import json
import logging
from typing import Any
from mangum import Mangum

from .main import app
from .services.analysis import run_pipeline
from .services.legal_analysis import run_legal_pipeline

logger = logging.getLogger("caseseva.lambda")

mangum_handler = Mangum(app, api_gateway_base_path="/")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    # Handle asynchronous Lambda invocation events (InvocationType='Event')
    if isinstance(event, dict) and "action" in event:
        action = event.get("action")
        case_id = str(event.get("case_id", ""))
        logger.info(f"Processing async Lambda event action='{action}' for case_id='{case_id}'")

        # Ensure app adapters are initialized for direct Lambda execution
        if not hasattr(app.state, "adapters") or app.state.adapters is None:
            from .adapters.factory import load_adapters
            app.state.adapters = load_adapters()

        try:
            if action == "engine0":
                from .services.ingestion import run_ingestion
                run_ingestion(app, case_id, understand=event.get("understand", False))
                return {"statusCode": 200}
            if action in {"engine1", "engine2", "engine3"}:
                if action == "engine1":
                    from .services.engine1 import run_engine1 as target
                elif action == "engine2":
                    from .services.engine2 import run_engine2 as target
                else:
                    from .services.engine3 import run_engine3 as target
                options = {key: event[key] for key in ("start_stage",) if key in event}
                target(app, case_id, **options)
                return {"statusCode": 200, "body": json.dumps({"status": "completed", "action": action})}
            if action == "run_pipeline":
                run_pipeline(
                    app,
                    case_id,
                    retry_failed=event.get("retry_failed", False),
                    requested_stages=event.get("requested_stages"),
                )
                return {"statusCode": 200, "body": json.dumps({"status": "completed", "action": action})}
            elif action == "run_legal_pipeline":
                run_legal_pipeline(
                    app,
                    case_id,
                    preserve_advocate_review=event.get("preserve_advocate_review", False),
                    retry_failed=event.get("retry_failed", False),
                    requested_stages=event.get("requested_stages"),
                )
                return {"statusCode": 200, "body": json.dumps({"status": "completed", "action": action})}
        except Exception as exc:
            logger.error(f"Error executing async Lambda pipeline '{action}': {exc}", exc_info=True)
            raise exc

    # Default API Gateway HTTP request handling
    return mangum_handler(event, context)
