import json
from datetime import datetime
from fastapi import APIRouter, HTTPException
from backend.app.database import get_db
from backend.app.schemas import BusinessProfile, OllamaHealth
from backend.app.services.ollama_service import check_ollama_health
from backend.app.config import settings

router = APIRouter(prefix="/settings", tags=["settings"])

@router.get("/health")
async def get_system_health():
    ollama_status = await check_ollama_health()
    
    # Check SQLite status
    db_ok = False
    lead_count = 0
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM leads")
            lead_count = cursor.fetchone()["count"]
            db_ok = True
    except Exception:
        db_ok = False

    return {
        "status": "online",
        "database": {
            "status": "connected" if db_ok else "error",
            "type": "SQLite (WAL mode)",
            "path": settings.DB_PATH,
            "leads_count": lead_count
        },
        "ollama": ollama_status.model_dump(),
        "meta": {
            "configured": bool(settings.META_APP_ID and settings.META_ACCESS_TOKEN),
            "status": "connected" if bool(settings.META_APP_ID and settings.META_ACCESS_TOKEN) else "not_configured"
        }
    }

@router.get("/profile", response_model=BusinessProfile)
def get_business_profile():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_settings WHERE key = 'business_profile'")
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Business profile not initialized")
        return json.loads(row["value"])

@router.put("/profile", response_model=BusinessProfile)
def update_business_profile(profile: BusinessProfile):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO app_settings (key, value, updated_at)
            VALUES ('business_profile', ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
        """, (json.dumps(profile.model_dump()), datetime.now().isoformat()))
        conn.commit()
        return profile

@router.get("/ollama", response_model=OllamaHealth)
async def get_ollama_detailed():
    return await check_ollama_health()
