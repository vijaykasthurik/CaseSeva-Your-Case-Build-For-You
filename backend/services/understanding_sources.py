"""Original-source indexing and conservative identities; no language-specific rules."""
import copy
import re
from datetime import datetime
import dateparser
from .case_blackboard import CaseBlackboard, digest, input_references, VersionConflict


class InputNotReady(ValueError):
    pass


def synchronized_raw(db, case_id):
    case = db.get("cases", case_id)
    if not case or case.get("status") == "DELETED":
        raise InputNotReady("Case unavailable")
    raw = case.get("raw_package") or {}
    expected_ids = {e["evidence_id"] for e in case.get("evidence", [])}
    if (raw.get("case_id") != case_id or raw.get("input_version") != case.get("input_version", 1)
            or set(raw.get("evidence_ids", [])) != expected_ids):
        raise InputNotReady("Current Phase 1 package is required")
    board = CaseBlackboard(db).sync_input(case_id)
    if board["case_id"] != case_id or board["data"]["input"] != input_references(case):
        raise VersionConflict("Phase 1 references changed during synchronization")
    if digest(db.get("cases", case_id).get("raw_package")) != board["data"]["input"]["raw_fingerprint"]:
        raise VersionConflict("Raw package changed during synchronization")
    return raw, board


def passages(raw, answers=()):
    result = []
    uploaded = set(raw.get("evidence_ids", []))
    for source in raw.get("provenance", []):
        text = source.get("original_text", "")
        # Never turn a pending extraction or its filename into readable evidence.
        if source.get("extraction_status") != "COMPLETED" or not text.strip():
            continue
        if source.get("evidence_id") and source["evidence_id"] not in uploaded:
            raise ValueError("Source has an invented uploaded Evidence ID")
        for match in re.finditer(r"[^\n]+", text):
            if not match.group().strip():
                continue
            # Bounded context, with original offsets retained exactly.
            for offset in range(match.start(), match.end(), 1800):
                end = min(offset + 1800, match.end())
                result.append({"passage": len(result), "source_id": source["source_id"], "start": offset, "end": end,
                               "text": text[offset:end], "evidence_id": source.get("evidence_id"),
                               "language_hint": source.get("language", "unknown"), "source_hash": source.get("text_hash")})
    for answer in answers or []:
        if answer["response"] == "ANSWER" and answer.get("value", "").strip():
            result.append({"passage": len(result), "source_id": answer["source_id"], "start": 0,
                           "end": len(answer["value"]), "text": answer["value"], "evidence_id": None,
                           "language_hint": "detect dynamically", "source_hash": digest(answer["value"])})
    if len(result) > 160 or sum(len(p["text"]) for p in result) > 65000:
        raise InputNotReady("Source context requires review/chunking before understanding")
    return result


def ground(selections, indexed):
    refs = []
    for selection in selections:
        index, excerpt = selection.passage, selection.excerpt
        if index >= len(indexed) or excerpt not in indexed[index]["text"]:
            raise ValueError("Source selection is not an exact original passage")
        source = indexed[index]
        offset = source["text"].index(excerpt)
        refs.append({"source_id": source["source_id"], "passage": index, "start": source["start"] + offset,
                     "end": source["start"] + offset + len(excerpt), "wording": excerpt,
                     "evidence_id": source["evidence_id"], "source_hash": source["source_hash"]})
    return refs


def checked_date(candidate, refs, indexed):
    value = candidate.model_dump()
    expression = value["expression"]
    if expression and not any(expression in r["wording"] for r in refs):
        raise ValueError("Date expression is not in cited original source")
    normalized = value["normalized"]
    if value["precision"] in {"UNKNOWN", "APPROXIMATE", "RANGE", "SEQUENCE_ONLY"}:
        if normalized is not None:
            raise ValueError("Uncertain date cannot acquire an exact date")
        return value
    if not expression:
        raise ValueError("A dated record requires an original expression")
    if not normalized:
        return {**value, "normalization_review_required": True}
    # A year may come from the same original narrative only if unambiguous.
    source_ids = {r["source_id"] for r in refs}
    years = set(re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", " ".join(p["text"] for p in indexed if p["source_id"] in source_ids)))
    parsed = dateparser.parse(expression, settings={"STRICT_PARSING": True, "DATE_ORDER": "DMY", "PREFER_LOCALE_DATE_ORDER": False})
    if parsed is None and len(years) == 1:
        parsed = dateparser.parse(expression + " " + next(iter(years)), settings={"STRICT_PARSING": True, "DATE_ORDER": "DMY", "PREFER_LOCALE_DATE_ORDER": False})
    if value["precision"] == "MONTH_ONLY":
        # Never add a day to a month-only statement.
        if not re.fullmatch(r"\d{4}-\d{2}", normalized):
            raise ValueError("Month precision cannot contain a day")
        return {**value, "normalized": None, "normalization_review_required": True}
    if parsed is None:
        # Preserve the source when a date parser lacks capability for its form.
        return {**value, "normalized": None, "normalization_review_required": True}
    if parsed.date().isoformat() != normalized:
        raise ValueError("Normalized date contradicts original expression")
    return value


def assign_ids(items, previous, prefix, id_field, *, anchor_field="identity_anchor"):
    """Exact anchors first; unique semantic keys preserve edited-record identity.

    Ambiguous matches become new reviewable records, never silent merges. Old
    records remain as superseded entries, so IDs are never reused or renumbered.
    """
    previous = previous or {}
    result, used = {}, set()
    number = max([int(k[len(prefix):]) for k in previous if re.fullmatch(re.escape(prefix) + r"\d+", k)] or [0])
    for item in items:
        identical = next((key for key, old in result.items() if old[anchor_field] == item[anchor_field]), None)
        if identical:
            result[identical]["source_refs"] = list({digest(r): r for r in result[identical]["source_refs"] + item.get("source_refs", [])}.values())
            continue
        matches = [key for key, old in previous.items() if key not in used and old.get(anchor_field) == item[anchor_field]]
        if not matches:
            matches = [key for key, old in previous.items() if key not in used and not old.get("superseded")
                       and old.get("semantic_key") == item.get("semantic_key")]
        identifier = matches[0] if len(matches) == 1 else None
        if identifier is None:
            number += 1
            identifier = f"{prefix}{number:03d}"
        used.add(identifier)
        result[identifier] = {**item, id_field: identifier, "superseded": False,
                              "identity_review_required": len(matches) > 1}
    for identifier, old in previous.items():
        if identifier not in result:
            result[identifier] = {**copy.deepcopy(old), "superseded": True}
    return result
