"""Fetch only registered, reviewed official download URLs; never use fixtures."""
import hashlib
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
from ..models.case import utc_now
from .legal_knowledge import LegalKnowledge


def refresh(case, knowledge=None):
    knowledge = knowledge or LegalKnowledge()
    items = []
    laws = case.get("case_file", {}).get("applicable_law", [])
    for law in laws:
        if law.get("removed"): continue
        url = law.get("source_url", "")
        source = next((s for s in knowledge.sources.values() if urlparse(url).hostname in s.get("hosts", [])), None)
        entry = {"provision_id": law["provision_id"], "source_url": url, "cache_retrieved_at": law.get("retrieved_at"), "status": "PENDING", "reason": "Official download access and source verification require review."}
        if source and source.get("enabled") and source.get("tier") == "PRIMARY" and source.get("terms_reviewed") and source.get("robots_reviewed"):
            try:
                def allowed(address):
                    parsed = urlparse(address)
                    if parsed.scheme != "https" or parsed.hostname not in source["hosts"] or parsed.username or parsed.password:
                        raise ValueError("Official source redirect is not permitted.")
                class Redirect(HTTPRedirectHandler):
                    def redirect_request(self, req, fp, code, msg, headers, newurl):
                        allowed(newurl)
                        return super().redirect_request(req, fp, code, msg, headers, newurl)
                allowed(url)
                with build_opener(Redirect()).open(Request(url, headers={"User-Agent": "CaseSeva official-source verification"}), timeout=15) as response:
                    content = response.read(20 * 1024 * 1024 + 1)
                    if len(content) > 20 * 1024 * 1024: raise ValueError("Official source exceeds size limit.")
                    if content.startswith(b"%PDF"):
                        import pymupdf
                        with pymupdf.open(stream=content, filetype="pdf") as document:
                            text = "\n".join(page.get_text() for page in document)
                    else:
                        from .exports import TextBlocks
                        parser = TextBlocks(); parser.feed(content.decode("utf-8"))
                        text = "\n".join(parser.blocks)
                if not law.get("quote") or law["quote"] not in text:
                    raise ValueError("The previously verified quotation does not match the current source.")
                entry.update({"status": "COMPLETE", "retrieved_at": utc_now(), "content_hash": hashlib.sha256(text.encode()).hexdigest(), "reason": "Exact quotation matched a current official download."})
            except Exception:
                entry["reason"] = "Current official-source verification failed. Cached material remains labelled with its original retrieval date and requires advocate confirmation."
        items.append(entry)
    return {"status": "COMPLETE" if items and all(item["status"] == "COMPLETE" for item in items) else "PENDING", "checked_at": utc_now(), "items": items, "procedure_note": "Current filing requirement requires advocate confirmation."}
