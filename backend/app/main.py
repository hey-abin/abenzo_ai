from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.config import settings
from backend.app.database import init_db
from backend.app.routers import leads, inbox, settings as app_settings, meta, knowledge

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

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
