"""Bounded discovery downloads; a downloaded document is NOT verified law."""
import hashlib
import time
from urllib.error import URLError, HTTPError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
from ...models.case import utc_now
from ...services.legal_knowledge import LegalKnowledge


class OfficialSourceAdapter:
    def __init__(self, knowledge=None):
        self.knowledge = knowledge or LegalKnowledge()

    def fetch(self, registry_id, url, *, attempts=2, on_download=None):
        if not 1 <= attempts <= 3:
            raise ValueError('Official retrieval permits one to three attempts')
        for attempt in range(attempts):
            try:
                return self._fetch(registry_id, url, on_download=on_download)
            except (TimeoutError, URLError) as exc:
                if isinstance(exc, HTTPError) and exc.code not in {408, 429, 500, 502, 503, 504}:
                    raise
                if attempt + 1 == attempts:
                    raise
                rate = self.knowledge.sources.get(registry_id, {}).get('rate_limit_per_minute', 2)
                time.sleep(max(1 + attempt, 60 / max(1, rate)))

    def _fetch(self, registry_id, url, *, on_download=None):
        source = self.knowledge.sources.get(registry_id)
        if not source or source.get('tier') != 'PRIMARY':
            raise ValueError('Official source registration required')
        def allowed(address):
            parsed = urlparse(address)
            if parsed.scheme != 'https' or parsed.hostname not in source['hosts'] or parsed.username or parsed.password or parsed.port not in (None, 443):
                raise ValueError('Unregistered official source address')
        class Redirect(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                allowed(newurl)
                return super().redirect_request(req, fp, code, msg, headers, newurl)
        allowed(url)
        with build_opener(Redirect()).open(Request(url, headers={'User-Agent': 'CaseSeva source discovery'}), timeout=20) as response:
            final_url = response.geturl()
            allowed(final_url)
            content = response.read(20 * 1024 * 1024 + 1)
            if len(content) > 20 * 1024 * 1024:
                raise ValueError('Source exceeds ingestion size limit')
        retrieved_at = utc_now()
        raw_hash = hashlib.sha256(content).hexdigest()
        if on_download:
            on_download({'final_url': final_url, 'retrieved_at': retrieved_at, 'raw_hash': raw_hash})
        if content.startswith(b'%PDF'):
            import pymupdf
            with pymupdf.open(stream=content, filetype='pdf') as document:
                text = '\n'.join(page.get_text() for page in document)
        else:
            from ...services.exports import TextBlocks
            parser = TextBlocks()
            parser.feed(content.decode('utf-8'))
            text = '\n'.join(parser.blocks)
        if not text.strip():
            raise ValueError('Official source could not be read')
        return {'registry_id': registry_id, 'official_url': url, 'final_url': final_url, 'retrieved_at': retrieved_at,
                'raw_hash': raw_hash, 'official_text': text,
                'content_hash': hashlib.sha256(text.encode()).hexdigest(), 'verification': 'PENDING'}
