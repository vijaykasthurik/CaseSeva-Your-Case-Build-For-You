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
from .real.auth import RealAuthAdapter
from .real.database import RealDatabaseAdapter
from .real.llm import RealLLMAdapter
from .real.storage import RealStorageAdapter
from .real.workflow import RealWorkflowAdapter
from .real.legal_retrieval import RealLegalRetrievalAdapter
from .mongo.database import MongoDatabaseAdapter
from .mongo.storage import MongoGridFSStorageAdapter

env_keys_before_dotenv = set(os.environ.keys())
env_vals_before_dotenv = {k: os.environ[k] for k in os.environ}
load_dotenv(override=False)


@dataclass
class AdapterSet:
    storage: StorageAdapter
    database: DatabaseAdapter
    llm: LLMAdapter
    auth: AuthAdapter
    workflow: WorkflowAdapter
    legal_retrieval: LegalRetrievalAdapter
    mode: str


def load_adapters() -> AdapterSet:
    if "USE_MOCK_AWS" in env_vals_before_dotenv:
        use_mock = env_vals_before_dotenv["USE_MOCK_AWS"].strip().lower() == "true"
    else:
        use_mock = os.getenv("USE_MOCK_AWS", "false").strip().lower() == "true"

    def is_explicitly_true(key: str) -> bool:
        if key in env_vals_before_dotenv:
            return env_vals_before_dotenv[key].strip().lower() == "true"
        if use_mock:
            return False
        return os.getenv(key, "false").strip().lower() == "true"

    use_real_llm = is_explicitly_true("USE_REAL_LLM")
    use_real_database = is_explicitly_true("USE_REAL_DATABASE")
    use_real_storage = is_explicitly_true("USE_REAL_STORAGE")
    if os.getenv("APP_ENV", "development").lower() in {"production", "prod"} and use_mock:
        raise RuntimeError("Production configuration refuses mock or hybrid processing.")



    db_provider = os.getenv("DATABASE_PROVIDER", "").strip().lower()
    obj_provider = os.getenv("OBJECT_STORE_PROVIDER", "").strip().lower()
    use_mongo = db_provider == "mongodb" or os.getenv("USE_MONGODB", "false").strip().lower() == "true"

    if use_mongo:
        database = MongoDatabaseAdapter()
        if obj_provider in {"mongodb", "gridfs", ""}:
            storage = MongoGridFSStorageAdapter()
        elif obj_provider in {"s3", "real"} or use_real_storage:
            storage = RealStorageAdapter()
        else:
            storage = MockStorageAdapter()
        llm = RealLLMAdapter() if use_real_llm else MockLLMAdapter()
        return AdapterSet(
            storage=storage,
            database=database,
            llm=llm,
            auth=MockAuthAdapter(database, seed_demo=False),
            workflow=MockWorkflowAdapter(database),
            legal_retrieval=RealLegalRetrievalAdapter() if not use_mock else MockLegalRetrievalAdapter(),
            mode="mongodb",
        )

    if use_mock and not (use_real_database or use_real_storage or use_real_llm):
        database = MockDatabaseAdapter()
        return AdapterSet(
            storage=MockStorageAdapter(),
            database=database,
            llm=MockLLMAdapter(),
            auth=MockAuthAdapter(database),
            workflow=MockWorkflowAdapter(database),
            legal_retrieval=MockLegalRetrievalAdapter(),
            mode="mock",
        )

    database = RealDatabaseAdapter() if (not use_mock or use_real_database) else MockDatabaseAdapter()
    storage = RealStorageAdapter() if (not use_mock or use_real_storage) else MockStorageAdapter()
    llm = RealLLMAdapter() if (not use_mock or use_real_llm) else MockLLMAdapter()

    return AdapterSet(
        storage=storage,
        database=database,
        llm=llm,
        auth=MockAuthAdapter(database, seed_demo=False),
        workflow=MockWorkflowAdapter(database),
        legal_retrieval=MockLegalRetrievalAdapter() if use_mock else RealLegalRetrievalAdapter(),
        mode="real" if not use_mock else "hybrid",
    )

