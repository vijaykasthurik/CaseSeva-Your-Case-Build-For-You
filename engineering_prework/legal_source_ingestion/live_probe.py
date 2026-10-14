"""Safe, polite read-only live discovery probe of official Indian legal portals.

Strict safety constraints:
- Read-only HTTP GET with conservative timeouts
- No bulk crawling
- No bypass of CAPTCHAs or access controls
- No modification of legal corpus or database state
- Records exact URLs, timestamps, headers, and SHA-256 digests
"""
import hashlib
import json
import ssl
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


PROBE_TARGETS = [
    ("india_code_new", "India Code Portal", "https://indiacode.gov.in/"),
    ("india_code_legacy", "India Code Legacy (Migration Notice)", "https://www.indiacode.nic.in/"),
    ("legislative_dept", "Legislative Department Portal", "https://legislative.gov.in/"),
    ("egazette_india", "eGazette Portal", "https://egazette.gov.in/"),
    ("doca_consumer", "Dept of Consumer Affairs", "https://consumeraffairs.nic.in/"),
    ("sci_judgments", "Supreme Court of India", "https://www.sci.gov.in/"),
    ("ecourts_judgments", "eCourts Judgment Search", "https://judgments.ecourts.gov.in/"),
    ("meity_portal", "MeitY Portal", "https://www.meity.gov.in/"),
    ("tn_stationery", "Tamil Nadu Stationery / Gazette", "https://stationeryprinting.tn.gov.in/"),
]


def run_probes() -> list[dict]:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    results = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CaseSevaResearchProbe/1.0"}

    for key, name, url in PROBE_TARGETS:
        entry = {
            "probe_key": key,
            "name": name,
            "probed_url": url,
            "probed_at": datetime.now(timezone.utc).isoformat(),
        }
        req = urllib.request.Request(url, headers=headers)
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=12, context=ctx) as resp:
                elapsed = int((time.time() - t0) * 1000)
                body = resp.read(8192)
                resp_headers = dict(resp.headers)

                entry["status_code"] = resp.status
                entry["final_url"] = resp.geturl()
                entry["latency_ms"] = elapsed
                entry["content_type"] = resp_headers.get("Content-Type", "")
                entry["server"] = resp_headers.get("Server", "")
                entry["rate_limit_limit"] = resp_headers.get("X-RateLimit-Limit")
                entry["rate_limit_remaining"] = resp_headers.get("X-RateLimit-Remaining")
                entry["bytes_downloaded"] = len(body)
                entry["sample_content_hash"] = hashlib.sha256(body).hexdigest()
                entry["captcha_clues_detected"] = any(
                    k in body.lower() for k in [b"captcha", b"recaptcha", b"challenge-running", b"cf-turnstile"]
                )
                entry["outcome"] = "SUCCESS"
        except Exception as exc:
            elapsed = int((time.time() - t0) * 1000)
            entry["latency_ms"] = elapsed
            entry["outcome"] = "FAILURE"
            entry["error_type"] = type(exc).__name__
            entry["error_message"] = str(exc)[:300]

        results.append(entry)
        time.sleep(1.0)  # Polite delay between requests

    return results


def main():
    print("Running safe read-only official sources probe...")
    report = run_probes()
    out_path = Path(__file__).parent / "live_probe_report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Report saved to {out_path} ({len(report)} sources probed).")


if __name__ == "__main__":
    main()
