from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.session import Base, engine
from app.db.migrations import ensure_runtime_schema
from app.routers import auth, dashboard, knowledge, settings, training
from app.services.llm_config import get_effective_llm_config


Base.metadata.create_all(bind=engine)
ensure_runtime_schema()

app = FastAPI(title="AI 销售陪练 MVP API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(knowledge.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(training.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")


@app.get("/api/health")
def health():
    config = get_effective_llm_config()
    return {
        "status": "ok",
        "llm_configured": config.configured,
        "llm_mode": config.mode,
    }
