import os
from dataclasses import dataclass

from dotenv import load_dotenv

from .auth import AuthAdapter
from .database import DatabaseAdapter
from .llm import LLMAdapter
from .storage import StorageAdapter
from .workflow import WorkflowAdapter
from .legal_retrieval import LegalRetrievalAdapter
from .mock.auth import MockAuthAdapter
from .mock.database import MockDatabaseAdapter
from .mock.llm import MockLLMAdapter
from .mock.storage import MockStorageAdapter
from .mock.workflow import MockWorkflowAdapter
from .mock.legal_retrieval import MockLegalRetrievalAdapter
from .real.llm import RealLLMAdapter
from .real.workflow import RealWorkflowAdapter
from .real.legal_retrieval import RealLegalRetrievalAdapter
from .mongo.database import MongoDatabaseAdapter
from .mongo.storage import MongoGridFSStorageAdapter
from .media import MediaAdapter
from .mock.media import MockMediaAdapter

load_dotenv(override=False)


class ProviderConfigurationError(RuntimeError):
    """Invalid explicit configuration; never select a fallback provider."""


def _flag(key: str) -> bool:
    value = os.environ.get(key, "false").strip().lower()
    if value not in {"true", "false"}:
        raise ProviderConfigurationError(f"{key} must be true or false")
    return value == "true"


def _provider(key, default, aliases):
    value = os.environ.get(key, default).strip().lower()
    if value not in aliases:
        # Do not echo arbitrary configuration values into public diagnostics.
        raise ProviderConfigurationError(f"Unsupported {key}")
    return aliases[value]


def derive_processing_mode(llm_mode, workflow_mode):
    if "unavailable" in {llm_mode, workflow_mode}:
        return "unavailable"
    if llm_mode == workflow_mode and llm_mode in {"mock", "live"}:
        return llm_mode
    if {llm_mode, workflow_mode} == {"mock", "live"}:
        return "hybrid"
    return "unavailable"


@dataclass
class AdapterSet:
    storage: StorageAdapter
    database: DatabaseAdapter
    llm: LLMAdapter
    auth: AuthAdapter
    workflow: WorkflowAdapter
    legal_retrieval: LegalRetrievalAdapter
    persistence_provider: str
    object_store_provider: str
    llm_provider: str
    workflow_provider: str
    email_provider: str = "disabled"
    media: MediaAdapter | None = None
    media_provider: str = "mock"

    @property
    def media_capabilities(self):
        if self.media:
            return self.media.get_capabilities()
        return {}

    @property
    def llm_processing_mode(self):
        return getattr(self.llm, "processing_capability", "unavailable")

    @property
    def workflow_processing_mode(self):
        return getattr(self.workflow, "processing_capability", "unavailable")

    @property
    def processing_mode(self):
        return derive_processing_mode(self.llm_processing_mode, self.workflow_processing_mode)

    @property
    def mode(self):
        """Deprecated, read-only alias for processing_mode, never persistence."""
        return self.processing_mode

    @property
    def providers(self):
        return {"database": self.persistence_provider, "object_store": self.object_store_provider,
                "llm": self.llm_provider, "workflow": self.workflow_provider}


def load_adapters() -> AdapterSet:
    # Resolve and validate ALL dimensions before any adapter has side effects.
    flags = {key: _flag(key) for key in ("USE_MOCK_AWS", "USE_REAL_DATABASE",
             "USE_REAL_STORAGE", "USE_REAL_LLM", "USE_MONGODB")}
    use_mock = flags["USE_MOCK_AWS"]
    db_default = "mongodb" if flags["USE_MONGODB"] else ("dynamodb" if flags["USE_REAL_DATABASE"] else ("mock" if use_mock else "mongodb"))
    db = _provider("DATABASE_PROVIDER", db_default,
                   {"mongodb": "mongodb", "mongo": "mongodb", "community": "mongodb", "mock": "mock", "dynamodb": "dynamodb", "real": "dynamodb"})
    storage = _provider("OBJECT_STORE_PROVIDER", "s3" if flags["USE_REAL_STORAGE"] else ("mock" if use_mock else "mongodb"),
                        {"mongodb": "mongodb", "gridfs": "mongodb", "local": "mongodb", "mock": "mock", "s3": "s3", "aws": "s3", "real": "s3"})
    llm = _provider("LLM_PROVIDER", "bedrock" if flags["USE_REAL_LLM"] else "mock",
                    {"mock": "mock", "bedrock": "bedrock", "real": "bedrock"})
    workflow = _provider("WORKFLOW_PROVIDER", "mock", {"mock": "mock", "real": "real"})
    email = _provider("EMAIL_PROVIDER", "disabled", {"disabled": "disabled", "mock": "mock", "ses": "ses"})
    llm_adapter = RealLLMAdapter() if llm == "bedrock" else MockLLMAdapter()
    workflow_capability = getattr(RealWorkflowAdapter, "processing_capability", "unavailable") if workflow == "real" else "mock"
    if os.getenv("APP_ENV", "development").lower() in {"production", "prod"}:
        mode = derive_processing_mode(getattr(llm_adapter, "processing_capability", "unavailable"), workflow_capability)
        if mode != "live":
            raise ProviderConfigurationError("Production configuration refuses mock, hybrid or unavailable processing.")
        if email == "mock":
            raise ProviderConfigurationError("Production configuration refuses mock email.")
    if db == "mongodb":
        database = MongoDatabaseAdapter()
    elif db == "mock":
        database = MockDatabaseAdapter()
    else:
        from .real.database import RealDatabaseAdapter
        database = RealDatabaseAdapter()
    if storage == "mongodb":
        object_store = MongoGridFSStorageAdapter()
    elif storage == "mock":
        object_store = MockStorageAdapter()
    else:
        from .real.storage import RealStorageAdapter
        object_store = RealStorageAdapter()
    media_val = os.environ.get("MEDIA_PROVIDER")
    if media_val is None:
        media_val = "aws" if _flag("ENABLE_AWS_MEDIA") else "mock"
    media = _provider("MEDIA_PROVIDER", media_val,
                      {"mock": "mock", "local": "mock", "aws": "aws", "real": "aws", "transcribe": "aws"})
    if media == "aws":
        from .real.media import RealMediaAdapter
        media_adapter = RealMediaAdapter(llm_adapter)
    else:
        media_adapter = MockMediaAdapter()
    return AdapterSet(
        storage=object_store, database=database,
        llm=llm_adapter,
        auth=MockAuthAdapter(database, seed_demo=use_mock and db == "mock"),
        workflow=RealWorkflowAdapter() if workflow == "real" else MockWorkflowAdapter(database),
        legal_retrieval=MockLegalRetrievalAdapter() if use_mock else RealLegalRetrievalAdapter(),
        persistence_provider=db, object_store_provider=storage, llm_provider=llm,
        workflow_provider=workflow, email_provider=email,
        media=media_adapter, media_provider=media,
    )
