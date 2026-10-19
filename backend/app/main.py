import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.config import settings
from backend.app.database import init_db
from backend.app.routers import leads, inbox, settings as app_settings, meta, knowledge

logger = logging.getLogger("abenzo.startup")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[Startup] Initiating application startup...")
    try:
        # Offload synchronous init_db to a worker thread with a 25-second timeout
        # to ensure the asyncio event loop remains responsive and Uvicorn can reach startup complete
        await asyncio.wait_for(asyncio.to_thread(init_db), timeout=25.0)
        logger.info("[Startup] Database initialization completed successfully.")
    except asyncio.TimeoutError:
        logger.error("[Startup] Database initialization timed out after 25s! Startup continuing to allow port binding and health checks.")
    except Exception as exc:
        logger.error("[Startup] Database initialization failed: %s. Startup continuing to allow port binding and health checks.", exc, exc_info=True)

    logger.info("[Startup] Application startup complete. Ready to receive requests.")
    yield
    logger.info("[Shutdown] Application shutdown complete.")

app = FastAPI(
    title="Abenzo AI Sales Assistant API",
    description="Local-first AI sales assistant for Abenzo Web Development Agency",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(leads.router, prefix="/api")
app.include_router(inbox.router, prefix="/api")
app.include_router(app_settings.router, prefix="/api")
app.include_router(meta.router, prefix="/api")
app.include_router(knowledge.router, prefix="/api")

@app.get("/api")
def root():
    return {
        "app": "Abenzo AI Sales Assistant",
        "version": "1.0.0",
        "status": "online",
        "documentation": "/docs"
    }
