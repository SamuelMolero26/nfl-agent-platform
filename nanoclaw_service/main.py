"""NanoClaw FastAPI application entry point.

NOTE: ``load_dotenv()`` MUST be called before any nanoclaw_service imports
because several modules read environment variables (e.g. ANTHROPIC_API_KEY,
SQLITE_PATH) at import time.  The ``# noqa: E402`` markers below suppress
the resulting PEP-8 import-order warnings intentionally.
"""
from dotenv import load_dotenv

load_dotenv()  # must be called before any service imports that read env vars at module level

from contextlib import asynccontextmanager  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from nanoclaw_service.config import settings  # noqa: E402
from nanoclaw_service.memory.sqlite_store import init_db  # noqa: E402
from nanoclaw_service.providers.http_client import close_clients, init_clients  # noqa: E402
from nanoclaw_service.routers.chat import router as chat_router  # noqa: E402
from nanoclaw_service.tools.registry import registry  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_clients(settings.providers)
    await registry.load(settings.tools, settings.providers)
    await init_db()
    yield
    await close_clients()


app = FastAPI(
    title="NanoClaw",
    description="NFL analytics agent — natural language interface to the data lake and ML models.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.server.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router, prefix="/chat", tags=["chat"])


@app.get("/health")
def health():
    return {"status": "ok", "service": "nanoclaw"}


@app.get("/tools")
def list_tools():
    return {"tools": registry.tool_manifest()}
