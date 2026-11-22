import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.database.init_db import init_database
from app.services.scheduler import start_scheduler, shutdown_scheduler
from app.api import (
    auth, documents, versions, chat, deadlines, 
    action_plans, notifications, nexus, admin
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("circulariq")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Database & Seed Baseline Data (skipped during fast test runs)
    if not os.environ.get("TESTING"):
        logger.info("Initializing CircularIQ Database and Baseline Knowledge...")
        init_database()
        start_scheduler()
    yield
    # Shutdown
    if not os.environ.get("TESTING"):
        shutdown_scheduler()

app = FastAPI(
    title="CircularIQ - Policy Intelligence & Deadline Management",
    version=settings.VERSION,
    description="Multi-Agent RAG System for Institutional Circular Intelligence, Version Tracking, and Deadline Orchestration.",
    lifespan=lifespan if not os.environ.get("TESTING") else None
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(documents.router, prefix=settings.API_V1_STR)
app.include_router(versions.router, prefix=settings.API_V1_STR)
app.include_router(chat.router, prefix=settings.API_V1_STR)
app.include_router(deadlines.router, prefix=settings.API_V1_STR)
app.include_router(action_plans.router, prefix=settings.API_V1_STR)
app.include_router(notifications.router, prefix=settings.API_V1_STR)
app.include_router(nexus.router, prefix=settings.API_V1_STR)
app.include_router(admin.router, prefix=settings.API_V1_STR)

@app.get("/")
def root():
    return {
        "app": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "operational",
        "docs_url": "/docs",
        "message": "CircularIQ Multi-Agent Policy Intelligence Engine running."
    }

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "database": "connected",
        "vector_store": "ready",
        "scheduler": "active"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
