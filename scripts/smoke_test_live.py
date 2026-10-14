#!/usr/bin/env python3
"""
Live End-to-End Smoke Test Script for CaseSeva AI Deployed Backend

Runs entirely against the deployed AWS Lambda / API Gateway endpoint:
1. Health Check GET /api/health
2. Sign up a unique client
3. Create a case draft
4. Update case with realistic story
5. Upload evidence file
6. Submit case for analysis
7. Trigger async AI pipeline POST /api/cases/{id}/analyze
8. Poll GET /api/cases/{id}/status until AWAITING_PREVIEW_1 or failure
"""

import argparse
import io
import json
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

REALISTIC_LAPTOP_STORY = (
    "I purchased a laptop online for personal use on 1 August 2026 for Rs. 78,999. "
    "The laptop was delivered on 3 August 2026. However, starting 7 August 2026, "
    "the laptop began shutting down repeatedly. I brought it to an authorised service centre "
    "on 10 August 2026, which inspected it and recorded a motherboard fault on the job sheet. "
    "On 12 August 2026, I requested a replacement laptop from the online seller as per their replacement policy. "
    "On 14 August 2026, the seller refused the replacement and offered only repair, despite the documented manufacturing defect."
)


def http_request(url: str, method: str = "GET", data: dict | None = None, headers: dict | None = None, files: dict | None = None) -> tuple[int, dict]:
    headers = dict(headers or {})
    body = None

    if files:
        boundary = f"----WebKitFormBoundary{random.randint(100000, 999999)}"
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        buffer = io.BytesIO()
        for field, (filename, content, content_type) in files.items():
            buffer.write(f"--{boundary}\r\n".encode("utf-8"))
            buffer.write(f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'.encode("utf-8"))
            buffer.write(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
            buffer.write(content if isinstance(content, bytes) else content.encode("utf-8"))
            buffer.write(b"\r\n")
        buffer.write(f"--{boundary}--\r\n".encode("utf-8"))
        body = buffer.getvalue()
    elif data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            resp_bytes = resp.read()
            resp_json = json.loads(resp_bytes.decode("utf-8")) if resp_bytes else {}
            return resp.status, resp_json
    except urllib.error.HTTPError as exc:
        err_bytes = exc.read()
        try:
            err_json = json.loads(err_bytes.decode("utf-8"))
        except Exception:
            err_json = {"raw": err_bytes.decode("utf-8", errors="ignore")}
        return exc.code, err_json


def main():
    parser = argparse.ArgumentParser(description="Live Smoke Test for CaseSeva AI Deployed Backend")
    parser.add_argument(
        "--base-url",
        default="https://d9a7s8hbid.execute-api.ap-southeast-2.amazonaws.com",
        help="Deployed API Gateway Base URL",
    )
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    print("=" * 70)
    print(f"🚀 STARTING LIVE SMOKE TEST AGAINST: {base_url}")
    print("=" * 70)

    # 1. Health Check
    print("\n1️⃣  Checking Backend Health (GET /api/health)...")
    status_code, health = http_request(f"{base_url}/api/health")
    if status_code != 200:
        print(f"❌ Health check failed with HTTP {status_code}: {health}")
        sys.exit(1)
    print(f"   ✅ Backend Status: {health.get('status')} | Providers: {health.get('providers')} | Processing: {health.get('processing_mode')}")

    # 2. Client Signup
    email = f"smoketest-{int(time.time())}-{random.randint(1000,9999)}@caseseva.test"
    print(f"\n2️⃣  Registering New Client ({email})...")
    signup_payload = {
        "full_name": "Live Smoke Test Client",
        "email": email,
        "mobile_number": "9876543210",
        "password": "Password123!",
        "preferred_language": "English",
        "state": "Delhi",
        "district_city": "New Delhi",
        "role": "client",
    }
    status_code, signup_resp = http_request(f"{base_url}/api/auth/signup", method="POST", data=signup_payload)
    if status_code != 201:
        print(f"❌ Signup failed with HTTP {status_code}: {signup_resp}")
        sys.exit(1)

    token = signup_resp.get("session_token")
    headers = {"Authorization": f"Bearer {token}"}
    print("   ✅ Account created & session token acquired.")

    # 3. Create Case
    print("\n3️⃣  Creating Case Draft (POST /api/cases)...")
    status_code, create_resp = http_request(f"{base_url}/api/cases", method="POST", headers=headers)
    if status_code != 200:
        print(f"❌ Case creation failed with HTTP {status_code}: {create_resp}")
        sys.exit(1)
    case_id = create_resp["case"]["case_id"]
    print(f"   ✅ Case created. ID: {case_id}")

    # 4. Patch Case Details
    print("\n4️⃣  Updating Case Story (PATCH /api/cases/{case_id})...")
    patch_payload = {
        "stage": "NEW_CONSULTATION",
        "stage_details": {},
        "client_story": REALISTIC_LAPTOP_STORY,
    }
    status_code, patch_resp = http_request(f"{base_url}/api/cases/{case_id}", method="PATCH", data=patch_payload, headers=headers)
    if status_code != 200:
        print(f"❌ Patching case failed with HTTP {status_code}: {patch_resp}")
        sys.exit(1)
    print("   ✅ Story and intake stage updated.")

    # 5. Upload Evidence
    print("\n5️⃣  Uploading Evidence File (POST /api/cases/{case_id}/evidence)...")
    evidence_file = {"file": ("invoice_receipt.txt", b"Official Laptop Purchase Receipt - Rs. 78,999 - Date: 1 Aug 2026", "text/plain")}
    status_code, upload_resp = http_request(f"{base_url}/api/cases/{case_id}/evidence", method="POST", headers=headers, files=evidence_file)
    if status_code != 200:
        print(f"❌ Evidence upload failed with HTTP {status_code}: {upload_resp}")
        sys.exit(1)
    print(f"   ✅ Evidence uploaded. ID: {upload_resp['evidence']['evidence_id']}")

    # 6. Submit Case
    print("\n6️⃣  Submitting Case (POST /api/cases/{case_id}/submit)...")
    status_code, submit_resp = http_request(f"{base_url}/api/cases/{case_id}/submit", method="POST", headers=headers)
    if status_code != 200:
        print(f"❌ Case submission failed with HTTP {status_code}: {submit_resp}")
        sys.exit(1)
    print(f"   ✅ Case submitted. Status: {submit_resp['case']['status']}")

    # 7. Trigger Async AI Pipeline
    print("\n7️⃣  Triggering Async AI Analysis Pipeline (POST /api/cases/{case_id}/analyze)...")
    status_code, analyze_resp = http_request(f"{base_url}/api/cases/{case_id}/analyze", method="POST", headers=headers)
    if status_code != 200:
        print(f"❌ Analysis trigger failed with HTTP {status_code}: {analyze_resp}")
        sys.exit(1)
    print(f"   ✅ Trigger Response: {analyze_resp}")

    # 8. Poll Status
    print("\n8️⃣  Polling Case Status (GET /api/cases/{case_id}/status)...")
    print("   ------------------------------------------------------------")
    start_time = time.time()
    max_timeout = 180  # 3 minutes
    last_status = None
    last_stages = {}

    while time.time() - start_time < max_timeout:
        status_code, status_resp = http_request(f"{base_url}/api/cases/{case_id}/status", headers=headers)
        if status_code == 200:
            current_status = status_resp.get("status")
            stage_statuses = status_resp.get("stage_statuses", {})
            error_details = status_resp.get("error")

            if current_status != last_status or stage_statuses != last_stages:
                elapsed = int(time.time() - start_time)
                stages_str = ", ".join([f"{k}:{v}" for k, v in stage_statuses.items()])
                print(f"   ⏱️  [{elapsed:3d}s] Case Status: {current_status:20s} | Stages: [{stages_str}]")
                last_status = current_status
                last_stages = stage_statuses

            if current_status == "AWAITING_PREVIEW_1":
                print("   ------------------------------------------------------------")
                print("\n🎉 SMOKE TEST SUCCESSFUL!")
                print(f"   Case {case_id} reached AWAITING_PREVIEW_1 in {int(time.time() - start_time)} seconds.")
                print("   Async self-invocation Lambda pipeline executed cleanly end-to-end on AWS Bedrock!")
                return

            if current_status == "ANALYSIS_FAILED":
                print("   ------------------------------------------------------------")
                print("\n❌ SMOKE TEST FAILED: Pipeline reached ANALYSIS_FAILED!")
                print(f"   Error details: {json.dumps(error_details, indent=2)}")
                print_cloudwatch_instructions()
                sys.exit(1)

        time.sleep(3)

    print("   ------------------------------------------------------------")
    print("\n⌛ SMOKE TEST TIMEOUT: Case did not reach AWAITING_PREVIEW_1 within 180 seconds.")
    print_cloudwatch_instructions()
    sys.exit(1)


def print_cloudwatch_instructions():
    print("\n🔍 TO INSPECT CLOUDWATCH LOGS FOR THE LIVE LAMBDA FUNCTION, RUN:")
    print("   aws logs tail /aws/lambda/caseseva-backend-dev --follow --region ap-southeast-2")


if __name__ == "__main__":
    main()
