"""Conservative, lossless-source canonicalization; never fuzzy-merge facts."""
import hashlib
import re
import unicodedata


def normalize(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def text_hash(text):
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


def detect_script_hint(text):
    """Unicode script hint only; script detection is never definitive language detection."""
    scripts = sorted({unicodedata.name(c, '').split(' ')[0] for c in text if c.isalpha()})
    return "script:" + "+".join(scripts) if scripts else "unknown"


def detect_language(text):
    """Weak script hint for backwards compatibility; real detection requires a LanguageDetectionProvider."""
    return detect_script_hint(text)


def canonicalize(sources):
    segments = []
    for source in sources:
        # Paragraph boundaries avoid treating amounts (Rs. 24,500) as sentences.
        for paragraph in re.split(r"\n\s*\n", source["original_text"]):
            text = normalize(paragraph)
            if not text:
                continue
            match = next((s for s in segments if s["text"] == text or (len(text) >= 40 and text in s["text"])), None)
            if match:
                if source["source_id"] not in match["source_ids"]: match["source_ids"].append(source["source_id"])
                continue
            # Collapse an identical narrative embedded in a longer transcript.
            contained = [s for s in segments if len(s["text"]) >= 40 and s["text"] in text]
            if contained:
                ids = list(dict.fromkeys([i for s in contained for i in s["source_ids"]] + [source["source_id"]]))
                first = segments.index(contained[0])
                segments = [s for s in segments if s not in contained]
                segments.insert(first, {"text": text, "source_ids": ids})
                continue
            # Exact suffix/prefix overlap only; conflicting dates/amounts stay separate.
            if segments:
                previous = segments[-1]
                a, b = previous["text"].split(), text.split()
                overlap = next((n for n in range(min(len(a), len(b)), 7, -1) if a[-n:] == b[:n]), 0)
                if overlap:
                    previous["text"] += " " + " ".join(b[overlap:])
                    if source["source_id"] not in previous["source_ids"]: previous["source_ids"].append(source["source_id"])
                    continue
            segments.append({"text": text, "source_ids": [source["source_id"]]})
    return {"text": "\n\n".join(s["text"] for s in segments), "segments": segments}
