from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .adapters.factory import load_adapters
from .routes.health import router as health_router
from .routes.auth import router as auth_router
from .routes.cases import router as cases_router
from .routes.analysis import router as analysis_router
from .routes.legal_analysis import router as legal_analysis_router
from .routes.advocates import router as advocates_router
from .routes.documents import router as documents_router
from .routes.engines import router as engines_router
from .routes.sharing import router as sharing_router
from .routes.review import router as review_router
from .routes.guest_claims import router as guest_claims_router
from .routes.clarification import router as clarification_router
from .routes.journey import router as journey_router
from .routes.retention import router as retention_router
from .routes.orchestration import router as orchestration_router
from .routes.authorities import router as authorities_router
from .routes.filing import router as filing_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.adapters = load_adapters()
    yield


import os

allowed_origins = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "https://main.d15hv8igdcecai.amplifyapp.com",
]
env_origin = os.getenv("ALLOWED_ORIGIN")
if env_origin and env_origin not in allowed_origins:
    allowed_origins.append(env_origin)

app = FastAPI(title="CaseSeva.ai", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"^https://.*\.amplifyapp\.com$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(cases_router)
app.include_router(analysis_router)
app.include_router(legal_analysis_router)
app.include_router(advocates_router)
app.include_router(documents_router)
app.include_router(engines_router)
app.include_router(sharing_router)
app.include_router(review_router)
app.include_router(guest_claims_router)
app.include_router(clarification_router)
app.include_router(journey_router)
app.include_router(retention_router)
app.include_router(orchestration_router)
app.include_router(authorities_router)
app.include_router(filing_router)
