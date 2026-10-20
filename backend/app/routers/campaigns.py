import asyncio
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query

from backend.app.database import get_db, _ph, _now_default
from backend.app.schemas import CampaignResponse, CampaignStartRequest, ResearchedHashtagItem
from backend.app.services.prospecting_service import (
    execute_prospecting_campaign,
    inspect_meta_hashtag_capabilities
)

logger = logging.getLogger("abenzo.campaigns_router")
router = APIRouter(prefix="/campaigns", tags=["prospecting_campaigns"])

def _format_campaign_row(row) -> Dict[str, Any]:
    c = dict(row)
    # Parse JSON fields safely
    for field in ("selected_hashtags_json", "meta_status_json", "provider_failures_json", "results_summary_json"):
        val = c.get(field)
        plain_key = field.replace("_json", "")
        if val:
            try:
                c[plain_key] = json.loads(val)
            except Exception:
                c[plain_key] = [] if "failures" in field or "summary" in field or "hashtags" in field else {}
        else:
            c[plain_key] = [] if "failures" in field or "summary" in field or "hashtags" in field else {}
        c.pop(field, None)
    return c


@router.post("/start", response_model=CampaignResponse)
async def start_prospecting_campaign(
    payload: Optional[CampaignStartRequest] = None,
    background_tasks: BackgroundTasks = None
):
    """
    Starts an autonomous AI prospecting campaign.
    Prevents concurrent duplicate campaigns and initiates background execution safely.
    """
    ph = _ph
    with get_db() as conn:
        cursor = conn.cursor()
        # 1. Prevent concurrent running campaigns
        cursor.execute("SELECT id, status, started_at FROM campaigns WHERE status = 'running'")
        active = cursor.fetchone()
        if active:
            raise HTTPException(
                status_code=409,
                detail=f"Campaign #{active['id']} is currently in progress (started at {active['started_at']}). Please wait for it to complete or cancel it before starting a new campaign."
            )

        # 2. Create new campaign record
        now = datetime.now().isoformat()
        cursor.execute(f"""
            INSERT INTO campaigns (
                status, stage, current_step_text, selected_hashtags_json,
                meta_status_json, discovered_posts_count, unique_profiles_count,
                qualified_prospects_count, drafts_generated_count, duplicates_count,
                rejected_count, provider_failures_json, results_summary_json,
                error_message, started_at, completed_at, created_at, updated_at
            ) VALUES (
                'running', 'checking_apis', 'Initiating autonomous campaign pipeline...',
                '[]', '{{}}', 0, 0, 0, 0, 0, 0, '[]', '[]', '', {ph(4)}
            )
        """, (now, "", now, now))
        campaign_id = cursor.lastrowid

        cursor.execute(f"SELECT * FROM campaigns WHERE id = {ph(1)}", (campaign_id,))
        camp_row = cursor.fetchone()

    # 3. Launch background execution task
    asyncio.create_task(execute_prospecting_campaign(campaign_id))

    return _format_campaign_row(camp_row)


@router.get("/active", response_model=Optional[CampaignResponse])
def get_active_campaign():
    """Returns the currently active campaign or the most recent campaign."""
    with get_db() as conn:
        cursor = conn.cursor()
        # Check running first
        cursor.execute("SELECT * FROM campaigns WHERE status = 'running' ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        if not row:
            # Fall back to latest campaign
            cursor.execute("SELECT * FROM campaigns ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()

        if not row:
            return None
        return _format_campaign_row(row)


@router.get("/meta-capabilities")
async def get_meta_capabilities():
    """Inspects Meta Graph API permissions and hashtag search support on-demand."""
    return await inspect_meta_hashtag_capabilities()


@router.get("/hashtags", response_model=List[ResearchedHashtagItem])
def list_researched_hashtags(limit: int = Query(50, ge=1, le=100)):
    """Returns all AI-researched hashtags and their historical yield in the CRM."""
    ph = _ph
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT hashtag, rationale, service_fit, times_used, last_used_at,
                   prospects_found, qualified_found
            FROM prospecting_hashtags
            ORDER BY last_used_at DESC, times_used DESC
            LIMIT {ph(1)}
        """, (limit,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


@router.get("", response_model=List[CampaignResponse])
def list_campaigns(limit: int = Query(20, ge=1, le=50)):
    """Lists recent prospecting campaigns."""
    ph = _ph
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM campaigns ORDER BY id DESC LIMIT {ph(1)}", (limit,))
        rows = cursor.fetchall()
        return [_format_campaign_row(r) for r in rows]


@router.get("/{campaign_id}", response_model=CampaignResponse)
def get_campaign_by_id(campaign_id: int):
    """Fetches details, status, and prospect queue for a specific campaign."""
    ph = _ph
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM campaigns WHERE id = {ph(1)}", (campaign_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Campaign #{campaign_id} not found")
        return _format_campaign_row(row)


@router.post("/{campaign_id}/cancel", response_model=CampaignResponse)
def cancel_campaign(campaign_id: int):
    """Cancels a running campaign gracefully."""
    ph = _ph
    now = datetime.now().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM campaigns WHERE id = {ph(1)}", (campaign_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Campaign #{campaign_id} not found")

        cursor.execute(f"""
            UPDATE campaigns SET
                status = 'cancelled',
                stage = 'cancelled',
                current_step_text = 'Campaign stopped by operator.',
                completed_at = {ph(1)},
                updated_at = {ph(1)}
            WHERE id = {ph(1)}
        """, (now, now, campaign_id))

        cursor.execute(f"SELECT * FROM campaigns WHERE id = {ph(1)}", (campaign_id,))
        updated = cursor.fetchone()
        return _format_campaign_row(updated)
