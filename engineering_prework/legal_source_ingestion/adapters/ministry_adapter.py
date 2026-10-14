"""Ministry portal interface; acquisition is not implemented.

A source-specific validated acquisition strategy and byte-bound evidence contract
are required before enabling retrieval. Registry metadata alone is insufficient.
"""
from .unsupported_adapter import UnsupportedSourceAdapter


class MinistryPortalAdapter(UnsupportedSourceAdapter):
    """Fails closed without actual retrieval evidence; never generates source text."""
