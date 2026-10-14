"""Processing guards never infer capability from a persistence or legacy mode."""


def llm_is_live(adapters):
    return getattr(adapters, "llm_processing_mode", "unavailable") == "live"


def processing_mode(adapters):
    return getattr(adapters, "processing_mode", "unavailable")


def llm_is_mock(adapters):
    return getattr(adapters, "llm_processing_mode", "unavailable") == "mock"
