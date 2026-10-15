"""Generates the deterministic human-review session manifest for the 12 active candidates."""
from datetime import datetime, timezone
import json
from pathlib import Path
import pymongo

ROOT = Path(__file__).resolve().parent.parent
QUEUE_PATH = ROOT / "docs" / "audits" / "phase4_review_queue.json"
MANIFEST_PATH = ROOT / "docs" / "audits" / "phase4_review_session_manifest.json"

TEMPORAL_CHECKLIST = [
    {
        "id": "exact_official_source_identity",
        "question": "Does the document come from the genuine official publisher with verified URL and raw GridFS hash?",
        "instruction": "Inspect official owner, registry ID, official canonical URL, and raw SHA-256."
    },
    {
        "id": "provision_text_matches_source",
        "question": "Does the extracted operative excerpt match the authoritative official enactment text verbatim?",
        "instruction": "Verify that no substantive statutory text has been invented, omitted, or corrupted."
    },
    {
        "id": "commencement_status",
        "question": "Has the provision officially commenced into force via gazetted notification?",
        "instruction": "Assess whether Section 1(3) commencement notifications have been gazetted for this section."
    },
    {
        "id": "amendments_coverage",
        "question": "Are all post-enactment statutory amendments reflected in the provision body?",
        "instruction": "Verify whether amending acts have inserted, substituted, or omitted text in this provision."
    },
    {
        "id": "repeal_omission_substitution",
        "question": "Has the provision been repealed, omitted, or superseded by later legislation?",
        "instruction": "Confirm that no subsequent repealing statute affects the operative standing of this provision."
    },
    {
        "id": "current_law_status",
        "question": "Does this provision represent current binding law as of the review date?",
        "instruction": "Assess whether any legal challenge or subsequent legislative act modifies its enforceability."
    },
    {
        "id": "territorial_applicability",
        "question": "What is the territorial extent and jurisdiction of this provision?",
        "instruction": "Check whether the provision applies to the whole of India, excludes specific states, or requires state consent."
    },
    {
        "id": "subordinate_legislation_relationships",
        "question": "Are there subordinate rules, regulations, or scheme notifications that alter operative effect?",
        "instruction": "Assess whether statutory rules have been framed under this section."
    },
    {
        "id": "consolidated_source_currentness",
        "question": "Is the official consolidated source (e.g., India Code) sufficiently current through today?",
        "instruction": "Check the consolidation cutoff date and determine if subsequent gazette notifications exist."
    },
    {
        "id": "additional_evidence_required",
        "question": "Is additional authenticated official gazette evidence required before approval?",
        "instruction": "If commencement or amendment lineage remains doubtful, request a new revision or mark stale."
    }
]

MANDATORY_WARNINGS = [
    "Current-law coverage has not been established.",
    "Do not infer that an official consolidated PDF is current through today.",
    "Amendment, commencement, and repeal coverage remain unverified pending independent authenticated human review."
]

ORDERED_SPECS = [
    # 1. DSPE Act 1946
    {"source_id": "dspe_act_1946_s1", "doc": "The Delhi Special Police Establishment Act, 1946", "sec": "1"},
    {"source_id": "dspe_act_1946_s2", "doc": "The Delhi Special Police Establishment Act, 1946", "sec": "2"},
    {"source_id": "dspe_act_1946_s3", "doc": "The Delhi Special Police Establishment Act, 1946", "sec": "3"},
    {"source_id": "dspe_act_1946_s6", "doc": "The Delhi Special Police Establishment Act, 1946", "sec": "6"},
    # 2. Information Technology Act 2000
    {"source_id": "it_act_2000_s1", "doc": "The Information Technology Act, 2000", "sec": "1"},
    {"source_id": "it_act_2000_s3", "doc": "The Information Technology Act, 2000", "sec": "3"},
    {"source_id": "it_act_2000_s43", "doc": "The Information Technology Act, 2000", "sec": "43"},
    {"source_id": "it_act_2000_s66", "doc": "The Information Technology Act, 2000", "sec": "66"},
    # 3. Code on Wages 2019
    {"source_id": "wages_code_2019_s1", "doc": "The Code on Wages, 2019", "sec": "1"},
    {"source_id": "wages_code_2019_s3", "doc": "The Code on Wages, 2019", "sec": "3"},
    {"source_id": "wages_code_2019_s5", "doc": "The Code on Wages, 2019", "sec": "5"},
    {"source_id": "wages_code_2019_s6", "doc": "The Code on Wages, 2019", "sec": "6"},
]


def generate_manifest():
    client = pymongo.MongoClient("mongodb://127.0.0.1:27017")
    db = client["caseseva"]

    queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    cand_by_id = {c["source_id"]: c for c in queue["candidates"]}

    session_items = []
    for idx, spec in enumerate(ORDERED_SPECS, start=1):
        sid = spec["source_id"]
        cand = cand_by_id[sid]
        vid = cand["version_id"]

        vdoc = db.legal_authority_versions.find_one({"id": vid})
        if not vdoc:
            raise RuntimeError(f"Missing version document {vid}")
        src = vdoc["source"]
        parent_vid = src.get("parent_revision")

        # Check for review receipt (must be None)
        receipt = db.legal_authority_reviews.find_one({"source_digest": vid})
        receipt_status = receipt["decision"] if receipt else "NONE"

        pkt_ref = f"docs/audits/review_packets/{sid}.json"

        item = {
            "session_step": idx,
            "source_id": sid,
            "current_corrected_version_id": vid,
            "document": spec["doc"],
            "section": spec["sec"],
            "packet_reference": pkt_ref,
            "status": "REVIEW_PENDING",
            "predecessor_revision": parent_vid,
            "review_receipt_status": receipt_status,
            "temporal_review_status": "PENDING",
            "raw_sha256": cand["raw_hash"],
            "gridfs_file_id": cand["gridfs_file_id"],
            "gridfs_key": cand["gridfs_key"],
            "retrieved_at": cand["retrieved_at"],
            "official_url": cand["official_url"],
        }
        session_items.append(item)

    manifest = {
        "manifest_title": "CaseSeva Phase-4 Authenticated Human Legal Review Session Manifest",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_candidates": len(session_items),
        "session_order_description": "Grouped strictly by enactment (1. DSPE Act 1946, 2. IT Act 2000, 3. Code on Wages 2019) and sorted by section number.",
        "mandatory_warnings": MANDATORY_WARNINGS,
        "temporal_review_checklist": TEMPORAL_CHECKLIST,
        "candidates": session_items,
    }

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Session manifest generated at {MANIFEST_PATH} with {len(session_items)} candidates.")
    return manifest


if __name__ == "__main__":
    generate_manifest()
