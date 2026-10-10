import json
import os
import threading


def dispatch(app, engine, case_id, **options):
    if os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        import boto3
        region = os.getenv("CASESEVA_AWS_REGION") or os.getenv("AWS_REGION", "ap-southeast-2")
        boto3.client("lambda", region_name=region).invoke(FunctionName=os.environ["AWS_LAMBDA_FUNCTION_NAME"], InvocationType="Event", Payload=json.dumps({"action": f"engine{engine}", "case_id": case_id, **options}).encode())
    else:
        if engine == 0:
            from .ingestion import run_ingestion
            target = run_ingestion
        elif engine == 1:
            from .engine1 import run_engine1
            target = run_engine1
        elif engine == 2:
            from .engine2 import run_engine2
            target = run_engine2
        else:
            from .engine3 import run_engine3
            target = run_engine3
        threading.Thread(target=target, args=(app, case_id), kwargs=options, daemon=True).start()
