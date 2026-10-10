import logging
from urllib.parse import urlparse

logger = logging.getLogger("caseseva.authorised_sources")

# Strict Allowlist of Verified Government Legal Portals (Strict TLS Verified Hosts Only)
AUTHORISED_DOMAINS = {
    "indiacode.nic.in",
    "www.indiacode.nic.in",
    "sci.gov.in",
    "www.sci.gov.in",
    "ecourts.gov.in",
    "www.ecourts.gov.in",
    "consumeraffairs.gov.in",
    "www.consumeraffairs.gov.in",
    "egazette.nic.in",
    "www.egazette.nic.in",
}


def is_authorised_url(url: str) -> bool:
    """Verifies if a URL belongs to the explicit allowlist of official Indian legal portals."""
    try:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.username or parsed.password:
            return False
        hostname = (parsed.hostname or "").lower().strip()
        if not hostname:
            return False

        # Match exact domain in verified allowlist
        if hostname in AUTHORISED_DOMAINS:
            return True

        return False
    except Exception as err:
        logger.warning(f"Error parsing URL '{url}': {err}")
        return False


def validate_authorised_url(url: str) -> str:
    """Validates URL against allowlist; raises ValueError if URL is from an unverified or unauthorized source."""
    if not is_authorised_url(url):
        logger.error(f"REFUSED non-allowlisted source URL: {url}")
        raise ValueError(f"URL '{url}' is not on the authorised legal source allowlist.")
    return url
