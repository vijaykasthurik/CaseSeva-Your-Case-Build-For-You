import tempfile
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.adapters.mock.database import MockDatabaseAdapter
from backend.adapters.mock.storage import MockStorageAdapter
from backend.adapters.mock.llm import MockLLMAdapter
from backend.adapters.mock.auth import MockAuthAdapter
from backend.routes.cases import router as cases
from backend.routes.auth import router as auth
from backend.routes.analysis import router as analysis


def test_app():
    directory = tempfile.TemporaryDirectory()
    db = MockDatabaseAdapter(directory.name + "/database.json")
    adapters = SimpleNamespace(database=db, storage=MockStorageAdapter(directory.name + "/uploads"), llm=MockLLMAdapter(), auth=MockAuthAdapter(db), email_provider="mock", mode="mock", processing_mode="mock", llm_processing_mode="mock")
    app = FastAPI()
    app.state.adapters = adapters
    for router in (cases, auth, analysis):
        app.include_router(router)
    return directory, app, TestClient(app)


def client_account(client, suffix="a"):
    response = client.post("/api/auth/signup", json={"full_name": "Test client", "email": f"{suffix}@example.com", "password": "Password123", "mobile_number": "9876543210", "preferred_language": "English", "state": "Tamil Nadu", "district_city": "Chennai"})
    body = response.json()
    return body["user"], {"Authorization": "Bearer " + body["session_token"]}
