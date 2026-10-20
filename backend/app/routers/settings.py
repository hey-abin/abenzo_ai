import json
from datetime import datetime
from fastapi import APIRouter, HTTPException
from backend.app.database import get_db
from backend.app.schemas import (
    BusinessProfile,
    OllamaHealth,
    AutomationSettings,
    AutomationSettingsResponse
)
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

    is_pg = settings.is_postgres
    return {
        "status": "online",
        "database": {
            "status": "connected" if db_ok else "error",
            "type": "Neon PostgreSQL (Cloud)" if is_pg else "SQLite 3 (WAL mode)",
            "engine": "postgresql" if is_pg else "sqlite",
            "path": "neon-cloud-production" if is_pg else settings.DB_PATH,
            "leads_count": lead_count
        },
        "ollama": ollama_status.model_dump(),
        "meta": {
            "configured": bool(settings.effective_instagram_app_id and settings.effective_instagram_token),
            "status": "connected" if bool(settings.effective_instagram_app_id and settings.effective_instagram_token) else "not_configured"
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


@router.get("/automation", response_model=AutomationSettingsResponse)
async def get_automation_settings():
    from backend.app.routers.meta import inspect_instagram_token

    defaults = {
        "auto_reply_enabled": True,
        "auto_reply_paused_global": False,
        "require_human_approval": False
    }

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_settings WHERE key = 'automation_settings'")
        row = cursor.fetchone()
        if row:
            try:
                defaults.update(json.loads(row["value"]))
            except Exception:
                pass
        else:
            # Sync with profile auto_reply_faq_enabled if present
            cursor.execute("SELECT value FROM app_settings WHERE key = 'business_profile'")
            p_row = cursor.fetchone()
            if p_row:
                try:
                    p_val = json.loads(p_row["value"])
                    defaults["auto_reply_enabled"] = bool(p_val.get("auto_reply_faq_enabled", True))
                except Exception:
                    pass

    token = settings.effective_instagram_token
    meta_info = await inspect_instagram_token(token)

    return AutomationSettingsResponse(
        auto_reply_enabled=defaults["auto_reply_enabled"],
        auto_reply_paused_global=defaults["auto_reply_paused_global"],
        require_human_approval=defaults["require_human_approval"],
        meta_status=meta_info
    )


@router.put("/automation", response_model=AutomationSettingsResponse)
async def update_automation_settings(cfg: AutomationSettings):
    from backend.app.routers.meta import inspect_instagram_token

    now = datetime.now().isoformat()
    val_str = json.dumps(cfg.model_dump())

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO app_settings (key, value, updated_at)
            VALUES ('automation_settings', ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
        """, (val_str, now))

        # Also sync auto_reply_faq_enabled to business_profile
        cursor.execute("SELECT value FROM app_settings WHERE key = 'business_profile'")
        p_row = cursor.fetchone()
        if p_row:
            try:
                p_dict = json.loads(p_row["value"])
                p_dict["auto_reply_faq_enabled"] = cfg.auto_reply_enabled
                cursor.execute("""
                    UPDATE app_settings SET value = ?, updated_at = ? WHERE key = 'business_profile'
                """, (json.dumps(p_dict), now))
            except Exception:
                pass

        conn.commit()

    token = settings.effective_instagram_token
    meta_info = await inspect_instagram_token(token)

    return AutomationSettingsResponse(
        auto_reply_enabled=cfg.auto_reply_enabled,
        auto_reply_paused_global=cfg.auto_reply_paused_global,
        require_human_approval=cfg.require_human_approval,
        meta_status=meta_info
    )
