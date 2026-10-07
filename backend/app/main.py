from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.db.session import Base, SessionLocal, engine
from app.db.migrations import ensure_runtime_schema
from app.config import validate_settings
from app.routers import auth, dashboard, knowledge, settings, training, voice
from app.seed_kb import seed_kb_from_folder
from app.services.llm_config import get_effective_llm_config
from app.services.report_details import backfill_normalized_tables
from app.services.voice import VoiceClient


Base.metadata.create_all(bind=engine)
ensure_runtime_schema()

for _warning in validate_settings():
    print(f"[config] {_warning}")

# Auto-import kb/ folder on first startup
try:
    _db = SessionLocal()
    _count = seed_kb_from_folder(_db)
    if _count:
        print(f"seed_kb: imported {_count} documents from kb/ folder")
    _backfill = backfill_normalized_tables(_db)
    if _backfill["documents"] or _backfill["reports"]:
        print(f"backfill: tags={_backfill['documents']} reports={_backfill['reports']}")
finally:
    _db.close()

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
app.include_router(voice.router, prefix="/api")


@app.get("/api/health")
def health():
    config = get_effective_llm_config()
    return {
        "status": "ok",
        "llm_configured": config.configured,
        "llm_mode": config.mode,
        "voice_configured": VoiceClient().configured,
    }


# Serve frontend static files
FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend" / "dist"

if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        # Serve static files or fallback to index.html for SPA routing
        file_path = FRONTEND_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIR / "index.html")
