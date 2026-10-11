"""Opt-in real input validation using fictional data only; no case database writes.
Run from repository root: .venv/Scripts/python scripts/validate-phase1-input.py --live
"""
import argparse
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.services.input_layer import extract_content, build_raw_package


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Allow billed Bedrock calls for fictional input")
    args = parser.parse_args()
    folder = ROOT / ".localdev/phase1-validation"
    folder.mkdir(parents=True, exist_ok=True)
    results = {}
    from PIL import Image, ImageDraw, ImageFont
    import pymupdf as fitz
    english = Image.new("RGB", (1800, 300), "white")
    font_path = Path("C:/Windows/Fonts/arial.ttf")
    font = ImageFont.truetype(str(font_path), 48) if font_path.exists() else ImageFont.load_default(size=48)
    ImageDraw.Draw(english).text((40, 60), "Invoice: Paid Rs. 24,500 on 3 Sep 2026.", font=font, fill="black")
    image_buffer = io.BytesIO(); english.save(image_buffer, format="PNG")
    inputs = [("english_image.png", image_buffer.getvalue()), ("english_screenshot.png", image_buffer.getvalue())]
    sample_dir = ROOT / "output/pdf/tamil-test-inputs"
    for name in ("tamil-case-story.pdf", "tamil-case-story.png"):
        path = sample_dir / name
        if path.exists(): inputs.append((name, path.read_bytes()))
        else: results[name] = {"status": "BLOCKED", "reason": "Existing fictional sample is not available on this host."}
    for label, content in [("english", image_buffer.getvalue()), ("tamil", (sample_dir / "tamil-case-story.png").read_bytes() if (sample_dir / "tamil-case-story.png").exists() else None)]:
        if content is None: continue
        with Image.open(io.BytesIO(content)) as image:
            width, height = image.size
        with fitz.open() as pdf:
            page = pdf.new_page(width=600, height=600 * height / width)
            page.insert_image(page.rect, stream=content)
            inputs.append((label + "_scanned.pdf", pdf.tobytes()))
    from docx import Document
    doc = Document(); doc.add_paragraph("தமிழ் receipt: 24,500 on 3 Sep 2026.")
    buf = io.BytesIO(); doc.save(buf); inputs.append(("mixed.docx", buf.getvalue()))
    inputs.append(("mixed.txt", "தமிழ் receipt: 24,500 on 3 Sep 2026.".encode()))
    for name, data in inputs:
        result = extract_content(data, name)
        results[name] = {"status": result["status"], "method": result["method"], "language": result["language"], "contains_amount": "24,500" in result["original_text"], "characters": len(result["original_text"]), "review_required": result.get("review_required"), "reason": result.get("reason")}
        (folder / (name + ".txt")).write_text(result["original_text"], encoding="utf-8")
    if args.live:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
        from backend.adapters.real.llm import RealLLMAdapter
        adapters = SimpleNamespace(mode="real", llm=RealLLMAdapter())
        stories = {"tamil": (ROOT / "backend/tests/fixtures/tamil_refrigerator.txt").read_text(encoding="utf-8"), "english": "I paid Rs. 24,500 on 3 Sep 2026. I have the receipt. I do not have a warranty card. I do not know the employee name.", "mixed": "நான் 24,500 செலுத்தினேன் on 3 Sep 2026. I have the receipt. உத்தரவாத அட்டை என்னிடம் இல்லை."}
        for label, story in stories.items():
            raw = build_raw_package({"case_id": "fictional-input-" + label, "client_story": story, "origin": "CITIZEN_SELF_SERVICE", "owner_user_id": "fictional-test", "preferred_language": "Tamil" if label != "english" else "English", "evidence": []}, adapters)
            (folder / (label + "-live-package.json")).write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
            if label == "tamil":
                required_dates = ("24,500", "செப்டம்பர் 3", "செப்டம்பர் 5", "செப்டம்பர் 9", "செப்டம்பர் 10", "செப்டம்பர் 20", "அக்டோபர் 1", "அக்டோபர் 10")
                assert all(token in raw["original_text"] for token in required_dates), "Tamil dates or amount were lost"
                assert len(raw["declared_evidence"]) == 3, "Expected receipt, bank record and screenshots"
                assert len(raw["unavailable_evidence"]) == 3, "Expected warranty, phone recording and written report"
                unknown_quotes = " ".join(i["quote"] for i in raw["unknown_details"])
                assert all(token in unknown_quotes for token in ("முழுப் பெயரும்", "சரியான தேதி", "உறுதியாகக் கூற முடியாது")), "Unknown details were lost"
                assert not raw["evidence_ids"], "A declaration was promoted to an uploaded file"
            results[label + "_bedrock"] = {"language_status": raw["language"]["status"], "declarations_status": raw["declaration_processing"]["status"], "original_preserved": raw["original_story"] == story, "evidence_ids": raw["evidence_ids"], "available": [i["label"] for i in raw["declared_evidence"]], "unavailable": [i["label"] for i in raw["unavailable_evidence"]], "unknown": [i["label"] for i in raw["unknown_details"]], "pending": raw["pending"]}
        results["bedrock_tokens"] = {"input": adapters.llm.total_input_tokens, "output": adapters.llm.total_output_tokens}
    (folder / "validation.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=True, indent=2))
    failed = [name for name, result in results.items() if result.get("status") not in {None, "COMPLETED"} or result.get("contains_amount") is False or result.get("language_status") not in {None, "COMPLETED"} or result.get("declarations_status") not in {None, "COMPLETED"}]
    if failed: raise SystemExit("Validation needs review: " + ", ".join(failed))

if __name__ == "__main__": main()
