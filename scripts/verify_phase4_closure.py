"""CLI command to evaluate Phase-4 Human Review Closure Gate against active database."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import json
from backend.adapters.mongo.database import MongoDatabaseAdapter
from backend.services.phase4_closure_gate import evaluate_phase4_closure


def main():
    adapter = MongoDatabaseAdapter(db_name="caseseva")
    result = evaluate_phase4_closure(adapter)

    print("=" * 60)
    print(f"GATE: {result['gate_name']}")
    print(f"STATUS: {result['gate_status']}")
    print(f"CAN CLOSE: {result['can_close']}")
    print(f"TOTAL REQUIRED CANDIDATES: {result['total_required_candidates']}")
    print(f"PENDING CANDIDATES: {result['pending_candidates_count']}")
    print(f"RESOLVED CANDIDATES: {result['resolved_candidates_count']}")
    print("=" * 60)
    print(f"\n{result['message']}\n")

    if result["blockers"]:
        print("EXACT REMAINING BLOCKERS:")
        for idx, b in enumerate(result["blockers"], 1):
            print(f"  [{idx:2d}] {b}")

    return 0 if result["can_close"] else 1


if __name__ == "__main__":
    sys.exit(main())
