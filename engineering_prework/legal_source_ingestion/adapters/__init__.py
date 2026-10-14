"""Adapters package for official legal source ingestion."""
from .indiacode_adapter import IndiaCodeAdapter
from .ministry_adapter import MinistryPortalAdapter
from .judgment_adapter import JudgmentSourceAdapter

__all__ = ["IndiaCodeAdapter", "MinistryPortalAdapter", "JudgmentSourceAdapter"]
