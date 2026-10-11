"""Opt-in fictional live Bedrock validation. Never connects to DynamoDB/Transcribe."""
import argparse
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SAMPLES = {
    "english": "Fictional test only. My name is Kavya. I bought a refrigerator from Sample Store for Rs. 24,500 on 3 September 2026 for home use. It was delivered on 5 September 2026. It stopped cooling on 9 September 2026. I asked the seller for repair or replacement. A technician visited but I do not know the exact date or the cause of the defect. I have the receipt but have not uploaded it. I have not filed a case.",
    "hindi": "केवल काल्पनिक परीक्षण। मेरा नाम काव्या है। मैंने घर के उपयोग के लिए 3 सितंबर 2026 को नमूना स्टोर से 24,500 रुपये में एक रेफ्रिजरेटर खरीदा। 5 सितंबर 2026 को इसकी डिलीवरी हुई। 9 सितंबर 2026 को उसने ठंडा करना बंद कर दिया। मैंने विक्रेता से मरम्मत या बदलने का अनुरोध किया। एक तकनीशियन आया था लेकिन मुझे उसकी आने की सही तारीख या खराबी का कारण नहीं पता। मेरे पास रसीद है, लेकिन मैंने इसे अपलोड नहीं किया है। मैंने कोई मुकदमा दायर नहीं किया है।",
    "telugu": "ఇది కల్పిత పరీక్ష మాత్రమే. నా పేరు కావ్య. ఇంటి ఉపయోగం కోసం 3 సెప్టెంబర్ 2026న నమూనా స్టోర్ నుండి రూ. 24,500కు ఒక రిఫ్రిజిరేటర్ కొన్నాను. 5 సెప్టెంబర్ 2026న డెలివరీ అయింది. 9 సెప్టెంబర్ 2026న చల్లబరచడం ఆగిపోయింది. మరమ్మతు చేయాలని లేదా మార్చాలని విక్రేతను అడిగాను. ఒక టెక్నీషియన్ వచ్చాడు కానీ వచ్చిన ఖచ్చితమైన తేదీ, లోపానికి కారణం నాకు తెలియదు. రసీదు నా దగ్గర ఉంది, కానీ అప్లోడ్ చేయలేదు. నేను కేసు దాఖలు చేయలేదు.",
    "mixed": "Fictional test only. என் பெயர் காவியா. I bought a refrigerator from Sample Store for home use on 3 September 2026 for Rs. 24,500. 5 September 2026 அன்று delivery வந்தது. 9 September 2026 அன்று cooling நின்றுவிட்டது. Seller-இடம் repair அல்லது replacement கேட்டேன். Technician வந்த சரியான தேதி தெரியாது. Receipt என்னிடம் உள்ளது, upload செய்யவில்லை. இதுவரை வழக்கு தாக்கல் செய்யவில்லை.",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cases", nargs="+", default=["english"])
    parser.add_argument("--resume", action="store_true", help="Resume latest fictional local case, never production")
    parser.add_argument("--answer-unknown", action="store_true", help="Submit explicit UNKNOWN to at most two fictional clarification batches")
    args = parser.parse_args()
    if not args.live:
        raise SystemExit("Pass --live to authorize billed fictional Bedrock validation")
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from backend.adapters.real.llm import RealLLMAdapter
    from backend.adapters.mock.database import MockDatabaseAdapter
    from backend.adapters.mock.storage import MockStorageAdapter
    from backend.services.core_workflow import run_core, CORE_VERSION, save_core_answers
    from backend.services.case_blackboard import CaseBlackboard
    folder = ROOT / ".localdev" / "phase3-live"
    folder.mkdir(parents=True, exist_ok=True)
    report_path = ROOT / "artifacts" / "phase3_core_validation.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {"cases": {}, "scope": "Fictional data, local persistence, real Bedrock only"}
    for language in args.cases:
        text = (ROOT / "backend/tests/fixtures/tamil_refrigerator.txt").read_text(encoding="utf-8") if language == "tamil" else SAMPLES[language]
        db_path = folder / (language + "-" + uuid4().hex[:8] + ".json")
        if args.resume:
            candidates = [p for p in folder.glob(language + '-*.json') if len(p.stem.removeprefix(language + '-')) == 8]
            db_path = max(candidates, key=lambda p: p.stat().st_mtime)
        db = MockDatabaseAdapter(db_path)
        llm = RealLLMAdapter()
        adapters = SimpleNamespace(database=db, llm=llm, storage=MockStorageAdapter(folder / "uploads"), mode="hybrid")
        if not args.resume:
            db.create("cases", {"id": language, "case_id": language, "owner_user_id": "fictional-test", "status": "SUBMITTED", "stage": "NEW_CONSULTATION",
                "workflow_version": 2, "engine1_execution": CORE_VERSION, "input_version": 1, "client_story": text, "evidence": [], "preferred_language": language})
        else:
            db.update('cases', language, {'core_retry_requested': True})
        print("Starting fictional live core:", language, flush=True)
        started = time.monotonic()
        run_core(SimpleNamespace(state=SimpleNamespace(adapters=adapters)), language)
        checkpoints = []
        for _ in range(2 if args.answer_unknown else 0):
            current = db.get('cases', language)
            if current['status'] != 'AWAITING_CLIENT_INFO':
                break
            batch = current['clarification_rounds'][-1]
            answers = [{'question_id': q['question_id'], 'response': 'UNKNOWN', 'value': '', 'evidence_ids': []} for q in batch['questions']]
            checkpoints.append({'status': current['status'], 'questions': len(answers), 'test_response': 'UNKNOWN'})
            save_core_answers(db, current, batch, answers, 'fictional-test')
            batch.update(status='ANSWERED', answers=answers)
            db.update('cases', language, {'clarification_rounds': current['clarification_rounds']})
            run_core(SimpleNamespace(state=SimpleNamespace(adapters=adapters)), language)
        board = CaseBlackboard(db).read_board(language)
        data = board["data"]
        case = db.get("cases", language)
        summary = {"case_status": case["status"], "resumed": args.resume, "clarification_checkpoints": checkpoints,
            "agents": {k: {"status": v["status"], "failure": v.get("failure_reason")} for k, v in board["nodes"].items()},
            "primary_domain": data.get("domain_classification", {}).get("primary_domain"),
            "stage": data.get("case_understanding", {}).get("stage", {}).get("stage"),
            "detected_languages": data.get("case_understanding", {}).get("stage", {}).get("language", {}).get("detected_languages"),
            "facts": len(data.get("facts", {})), "incidents": len(data.get("incidents", {})), "timeline": len(data.get("timeline", {})), "parties": len(data.get("parties", {})),
            "uploaded_evidence_ids": case.get("raw_package", {}).get("evidence_ids"),
            "legal_foundation": case.get("legal_foundation_status"), "model": llm.model_id,
            "provider_attempts": sum(sum(bool(entry.get(k)) for k in ("attempt_1", "attempt_2")) for entry in llm.stage_logs),
            "input_tokens": llm.total_input_tokens, "output_tokens": llm.total_output_tokens, "seconds": round(time.monotonic() - started, 1)}
        summary['checks'] = {
            'all_seven_completed': len(board['nodes']) == 7 and all(n['status'] == 'COMPLETED' for n in board['nodes'].values()),
            'consumer_domain': summary['primary_domain'] == 'CONSUMER',
            'new_consultation': summary['stage'] == 'NEW_CONSULTATION',
            'no_invented_uploads': not summary['uploaded_evidence_ids'] and all(not f['evidence_ids'] for f in data.get('facts', {}).values()),
            'no_premature_legal_foundation': summary['legal_foundation'] == 'PENDING' and not case.get('case_file'),
            'unknown_dates_not_fabricated': all(f['date'].get('normalized') is None for f in data.get('facts', {}).values() if f['date']['precision'] in {'UNKNOWN', 'APPROXIMATE', 'RANGE', 'SEQUENCE_ONLY'}),
        }
        if language in report["cases"]:
            report.setdefault("prior_runs", []).append({"language": language, **report["cases"][language]})
        report["cases"][language] = summary
        report_path.parent.mkdir(exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        detail = json.dumps({"database_path": str(db_path), "board": board, "case": case, "model_logs": llm.stage_logs}, ensure_ascii=False, indent=2)
        (folder / (language + "-details.json")).write_text(detail, encoding="utf-8")
        (folder / (language + '-run-' + uuid4().hex[:8] + '.json')).write_text(detail, encoding='utf-8')
        print(json.dumps(summary, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
