"""Interactive / Scripted Safe Review Session Harness CLI.

Allows an authenticated qualified advocate (role=advocate, status=VERIFIED,
capability=LEGAL_AUTHORITY_REVIEW) to inspect Phase-4 candidates and submit
legal decisions with immutable receipts and staleness protection.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.adapters.mongo.database import MongoDatabaseAdapter
from backend.services.review_session_harness import ReviewSessionHarness


def run_session(reviewer_email: str, non_interactive: bool = False):
    adapter = MongoDatabaseAdapter(db_name="caseseva")
    harness = ReviewSessionHarness(adapter)

    # 1. Lookup and verify reviewer
    users = [u for u in adapter.list("users") if u.get("email") == reviewer_email]
    if not users:
        print(f"ERROR: Reviewer account '{reviewer_email}' not found.")
        return 1

    reviewer = users[0]
    try:
        harness.verify_reviewer_eligibility(reviewer)
        print(f"AUTHENTICATED REVIEWER: {reviewer['email']} (Advocate, Verified, Capability: LEGAL_AUTHORITY_REVIEW)")
    except PermissionError as exc:
        print(f"PERMISSION DENIED: {exc}")
        return 1

    manifest = harness.get_manifest()
    candidates = manifest.get("candidates", [])
    print(f"\nLoaded {len(candidates)} candidates from session manifest.\n")

    for item in candidates:
        sid = item["source_id"]
        vid = item["current_corrected_version_id"]
        doc_title = item["document"]
        sec_num = item["section"]

        print("=" * 70)
        print(f"SESSION STEP {item['session_step']} OF {len(candidates)}: {sid}")
        print(f"Document: {doc_title} | Section: {sec_num}")
        print(f"Current Expected Version ID: {vid}")
        print(f"Predecessor Revision ID:     {item['predecessor_revision']}")
        print("=" * 70)

        # Load packet
        try:
            packet = harness.get_candidate_packet(sid)
        except Exception as exc:
            print(f"Error loading packet: {exc}")
            continue

        print("\n--- EXACT OFFICIAL OPERATIVE EXCERPT ---")
        print(packet.get("exact_official_excerpt", "").strip())
        print("----------------------------------------")

        print("\n--- MANDATORY TEMPORAL WARNINGS ---")
        for w in packet.get("temporal_warnings", []):
            print(f"  [!] {w}")

        print("\n--- TEMPORAL REVIEW CHECKLIST ---")
        for cl in manifest.get("temporal_review_checklist", []):
            print(f"  [?] {cl['question']}")

        if non_interactive:
            print("\n[Non-interactive inspection completed for candidate]")
            continue

        print("\nDecision Options: 1=REVIEWED_PRIMARY, 2=REJECTED, 3=STALE, 4=NEEDS_NEW_REVISION, S=Skip, Q=Quit")
        choice = input("Select decision: ").strip().upper()
        if choice == "Q":
            print("Session paused by reviewer.")
            break
        elif choice == "S":
            res = harness.skip_candidate(sid)
            print(f"  -> {res['message']}")
            continue

        decision_map = {
            "1": "REVIEWED_PRIMARY",
            "2": "REJECTED",
            "3": "STALE",
            "4": "NEEDS_NEW_REVISION",
        }
        dec = decision_map.get(choice)
        if not dec:
            print("Invalid choice; candidate skipped.")
            continue

        note = input("Enter human legal review rationale/reason: ").strip()
        if not note:
            print("Rationale cannot be empty; candidate skipped.")
            continue

        try:
            result = harness.submit_decision(
                source_id=sid,
                expected_version=vid,
                reviewer=reviewer,
                decision=dec,
                note=note,
            )
            print(f"\nDECISION RECORDED SUCCESSFULLY:")
            print(f"  Receipt ID: {result['review_receipt_id']}")
            print(f"  Decision:   {result['decision']}")
        except Exception as exc:
            print(f"SUBMISSION FAILED: {exc}")

    return 0


def main():
    parser = argparse.ArgumentParser(description="CaseSeva Human Review Session Harness")
    parser.add_argument("--reviewer", help="Email of authenticated qualified advocate")
    parser.add_argument("--inspect-only", action="store_true", help="Inspect all candidates non-interactively")
    args = parser.parse_args()

    if not args.reviewer:
        print("Usage: python scripts/human_review_session.py --reviewer <advocate_email> [--inspect-only]")
        print("\nNote: Only a verified advocate with LEGAL_AUTHORITY_REVIEW capability may authenticate.")
        return 1

    return run_session(args.reviewer, non_interactive=args.inspect_only)


if __name__ == "__main__":
    sys.exit(main())
