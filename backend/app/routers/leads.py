import json
import csv
import io
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Response
from typing import Optional, List
from backend.app.config import settings
from backend.app.database import get_db
from backend.app.schemas import (
    LeadCreate,
    LeadUpdate,
    LeadResponse,
    LeadDiscoveryQuery,
    LeadDiscoveryResponse,
    ImportDiscoveredRequest,
    LeadSendMessageRequest,
    LeadSendMessageResponse,
    LeadMessagingStatusResponse
)
from backend.app.services.website_checker import check_website
from backend.app.services.ollama_service import qualify_lead_with_ai
from backend.app.services.discovery_service import check_duplicate_lead, execute_lead_discovery, evaluate_digital_opportunity

router = APIRouter(prefix="/leads", tags=["leads"])

def row_to_lead(row) -> dict:
    d = dict(row)
    if isinstance(d.get("evidence_json"), str):
        try:
            d["evidence_json"] = json.loads(d["evidence_json"] or "{}")
        except Exception:
            d["evidence_json"] = {}
    if isinstance(d.get("score_breakdown_json"), str):
        try:
            d["score_breakdown_json"] = json.loads(d["score_breakdown_json"] or "{}")
        except Exception:
            d["score_breakdown_json"] = {}
    for key in (
        "city", "instagram_handle", "contact_name", "public_phone", "public_email",
        "suggested_service", "observed_problems", "project_timeline", "budget",
        "consent_source", "follow_up_date", "outreach_action_at",
        "source_media_id", "source_media_url", "source_caption", "discovery_hashtag"
    ):
        if d.get(key) is None:
            d[key] = ""
    if "campaign_id" not in d:
        d["campaign_id"] = None
    return d

@router.get("/metrics")
def get_leads_metrics():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as total FROM leads")
        total_leads = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as total FROM leads WHERE lead_score >= 60")
        qualified_leads = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as total FROM leads WHERE outreach_status IN ('draft_ready', 'new') AND personalized_dm != ''")
        drafts_waiting = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as total FROM conversations WHERE needs_human = 1 AND status = 'active'")
        inbox_needing_attention = cursor.fetchone()["total"]

        cursor.execute("SELECT id, business_name, outreach_status, lead_score, updated_at FROM leads ORDER BY updated_at DESC LIMIT 5")
        recent_leads = [dict(r) for r in cursor.fetchall()]

        return {
            "total_leads": total_leads,
            "qualified_leads": qualified_leads,
            "drafts_waiting": drafts_waiting,
            "inbox_needing_attention": inbox_needing_attention,
            "recent_activity": recent_leads
        }

@router.get("", response_model=List[LeadResponse])
def get_leads(
    industry: Optional[str] = None,
    state: Optional[str] = None,
    website_status: Optional[str] = None,
    outreach_status: Optional[str] = None,
    search: Optional[str] = None,
    min_score: Optional[int] = None
):
    with get_db() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM leads WHERE 1=1"
        params = []

        if industry:
            query += " AND LOWER(industry) LIKE ?"
            params.append(f"%{industry.lower().strip()}%")
        if state:
            query += " AND LOWER(state) LIKE ?"
            params.append(f"%{state.lower().strip()}%")
        if website_status:
            query += " AND website_status = ?"
            params.append(website_status)
        if outreach_status:
            query += " AND outreach_status = ?"
            params.append(outreach_status)
        if min_score is not None:
            query += " AND lead_score >= ?"
            params.append(min_score)
        if search:
            query += " AND (LOWER(business_name) LIKE ? OR LOWER(business_summary) LIKE ?)"
            params.append(f"%{search.lower().strip()}%")
            params.append(f"%{search.lower().strip()}%")

        query += " ORDER BY id DESC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [row_to_lead(r) for r in rows]

@router.post("", response_model=LeadResponse)
async def create_lead(lead_in: LeadCreate):
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Deduplication check
        dup = check_duplicate_lead(
            cursor,
            lead_in.business_name,
            lead_in.website_url or "",
            lead_in.instagram_url or lead_in.instagram_handle or ""
        )
        if dup:
            raise HTTPException(
                status_code=409,
                detail=f"Lead already exists: '{dup['business_name']}' (matched by {dup['matched_by']}, ID #{dup['id']})"
            )

        now = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO leads (
                business_name, industry, state, city, source_url, instagram_url, instagram_handle,
                website_url, website_status, evidence_json, contact_name, public_phone, public_email,
                project_timeline, budget, consent_source, follow_up_date, outreach_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'uncertain', '{}', ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?)
        """, (
            lead_in.business_name.strip(),
            lead_in.industry.strip() if lead_in.industry else "",
            lead_in.state.strip() if lead_in.state else "",
            lead_in.city.strip() if lead_in.city else "",
            lead_in.source_url.strip() if lead_in.source_url else "",
            lead_in.instagram_url.strip() if lead_in.instagram_url else "",
            lead_in.instagram_handle.strip() if lead_in.instagram_handle else "",
            lead_in.website_url.strip() if lead_in.website_url else "",
            lead_in.contact_name.strip() if lead_in.contact_name else "",
            lead_in.public_phone.strip() if lead_in.public_phone else "",
            lead_in.public_email.strip() if lead_in.public_email else "",
            lead_in.project_timeline.strip() if lead_in.project_timeline else "",
            lead_in.budget.strip() if lead_in.budget else "",
            lead_in.consent_source.strip() if lead_in.consent_source else "",
            lead_in.follow_up_date.strip() if lead_in.follow_up_date else "",
            now, now
        ))
        lead_id = cursor.lastrowid
        conn.commit()

    # Automatically run initial website check if website_url is supplied
    if lead_in.website_url:
        check_res = await check_website(lead_in.website_url)
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE leads SET
                    website_status = ?,
                    evidence_json = ?,
                    updated_at = ?
                WHERE id = ?
            """, (
                check_res.status,
                json.dumps(check_res.model_dump()),
                datetime.now().isoformat(),
                lead_id
            ))
            conn.commit()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
        row = cursor.fetchone()
        return row_to_lead(row)

@router.get("/{lead_id}", response_model=LeadResponse)
def get_lead_by_id(lead_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Lead not found")
        return row_to_lead(row)

@router.patch("/{lead_id}", response_model=LeadResponse)
def update_lead(lead_id: int, lead_in: LeadUpdate):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
        existing = cursor.fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Lead not found")

        updates = []
        params = []
        data = lead_in.model_dump(exclude_unset=True)

        if "outreach_status" in data and "outreach_action_at" not in data:
            data["outreach_action_at"] = datetime.now().isoformat()

        for key, val in data.items():
            if key in ("evidence_json", "score_breakdown_json") and isinstance(val, dict):
                val = json.dumps(val)
            updates.append(f"{key} = ?")
            params.append(val)

        if updates:
            updates.append("updated_at = ?")
            params.append(datetime.now().isoformat())
            params.append(lead_id)
            cursor.execute(f"UPDATE leads SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()

        cursor.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
        return row_to_lead(cursor.fetchone())

@router.delete("/{lead_id}")
def delete_lead(lead_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM leads WHERE id = ?", (lead_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Lead not found")
        cursor.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
        conn.commit()
        return {"status": "success", "message": f"Lead {lead_id} removed"}

@router.post("/{lead_id}/check-website", response_model=LeadResponse)
async def trigger_website_check(lead_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
        lead = cursor.fetchone()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

    check_res = await check_website(lead["website_url"])
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE leads SET
                website_status = ?,
                evidence_json = ?,
                updated_at = ?
            WHERE id = ?
        """, (
            check_res.status,
            json.dumps(check_res.model_dump()),
            datetime.now().isoformat(),
            lead_id
        ))
        conn.commit()
        cursor.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
        return row_to_lead(cursor.fetchone())

@router.post("/{lead_id}/qualify-ai", response_model=LeadResponse)
async def trigger_ai_qualification(lead_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
        lead = cursor.fetchone()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        
        cursor.execute("SELECT value FROM app_settings WHERE key = 'business_profile'")
        profile_row = cursor.fetchone()
        agency_profile = json.loads(profile_row["value"]) if profile_row else {}

    lead_dict = row_to_lead(lead)
    
    # Run Ollama inference
    try:
        ai_output = await qualify_lead_with_ai(lead_dict, agency_profile)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ollama qualification failed: {str(e)}")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE leads SET
                business_summary = ?,
                lead_score = ?,
                confidence = ?,
                opportunity = ?,
                recommended_service = ?,
                personalized_dm = ?,
                reasoning_summary = ?,
                next_best_action = ?,
                outreach_status = CASE WHEN outreach_status = 'new' THEN 'draft_ready' ELSE outreach_status END,
                updated_at = ?
            WHERE id = ?
        """, (
            ai_output.business_summary,
            ai_output.lead_score,
            ai_output.confidence,
            ai_output.opportunity,
            ai_output.recommended_service,
            ai_output.personalized_dm,
            ai_output.reasoning_summary,
            ai_output.next_best_action,
            datetime.now().isoformat(),
            lead_id
        ))
        conn.commit()
        cursor.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
        return row_to_lead(cursor.fetchone())

@router.post("/import-csv")
async def import_leads_csv(file: UploadFile = File(...)):
    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    imported = 0
    skipped = 0
    errors = []

    with get_db() as conn:
        cursor = conn.cursor()
        now = datetime.now().isoformat()

        for idx, row in enumerate(reader, start=2):
            name = row.get("business_name") or row.get("name") or row.get("Business Name") or ""
            name = name.strip()
            if not name:
                skipped += 1
                errors.append(f"Row {idx}: missing business_name")
                continue

            website = row.get("website_url") or row.get("website") or row.get("Website") or ""
            instagram = row.get("instagram_url") or row.get("instagram") or row.get("Instagram") or ""
            industry = row.get("industry") or row.get("Industry") or ""
            state = row.get("state") or row.get("State") or ""
            source = row.get("source_url") or row.get("source") or "CSV Import"

            # Deduplication
            dup = check_duplicate_lead(cursor, name, website, instagram)
            if dup:
                skipped += 1
                errors.append(f"Row {idx}: duplicate of existing lead #{dup['id']} ('{dup['business_name']}')")
                continue

            cursor.execute("""
                INSERT INTO leads (
                    business_name, industry, state, source_url, instagram_url, website_url,
                    website_status, evidence_json, outreach_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'uncertain', '{}', 'new', ?, ?)
            """, (name, industry.strip(), state.strip(), source.strip(), instagram.strip(), website.strip(), now, now))
            imported += 1

        conn.commit()

    return {
        "status": "success",
        "imported": imported,
        "skipped": skipped,
        "details": errors
    }

@router.get("/export-csv")
def export_leads_csv():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM leads ORDER BY id ASC")
        rows = cursor.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "business_name", "industry", "state", "source_url", "instagram_url",
        "website_url", "website_status", "lead_score", "confidence", "opportunity",
        "recommended_service", "personalized_dm", "outreach_status", "created_at"
    ])
    for r in rows:
        writer.writerow([
            r["id"], r["business_name"], r["industry"], r["state"], r["source_url"],
            r["instagram_url"], r["website_url"], r["website_status"], r["lead_score"],
            r["confidence"], r["opportunity"], r["recommended_service"], r["personalized_dm"],
            r["outreach_status"], r["created_at"]
        ])

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=abenzo_leads.csv"}
    )

@router.post("/discover", response_model=LeadDiscoveryResponse)
async def discover_public_leads(query_in: LeadDiscoveryQuery):
    """
    Discovers publicly listed businesses via Instagram-first search and public business directories.
    Excludes listicles, wholesale portals, blogs, and non-profile URLs.
    Never fabricates results.
    """
    niche = (query_in.niche or "").strip()
    city_or_state = (query_in.city_or_state or "").strip()
    keywords = (query_in.keywords or "").strip()
    limit = max(1, min(query_in.limit or 10, 25))

    if not niche and not keywords:
        raise HTTPException(status_code=400, detail="Please enter a business niche or search keywords.")

    with get_db() as conn:
        cursor = conn.cursor()
        try:
            res = await execute_lead_discovery(
                cursor,
                niche=niche,
                city_or_state=city_or_state,
                keywords=keywords,
                source_mode=query_in.source_mode or "instagram_only",
                stage=query_in.stage or "all",
                website_filter=query_in.website_filter or "all",
                min_score=query_in.min_score or 0,
                exclude_crm=bool(query_in.exclude_crm),
                limit=limit,
                search_provider=query_in.search_provider
            )
            return LeadDiscoveryResponse(**res)
        except Exception as e:
            return LeadDiscoveryResponse(
                status="error",
                query=f"{niche} in {city_or_state} {keywords}".strip(),
                provider="Instagram Business Discovery",
                results=[],
                total_found=0,
                source_mode=query_in.source_mode or "instagram_only",
                limitation_notice="Discovery search encountered an error. Please adjust criteria or retry.",
                error_message=str(e),
                diagnostics=None
            )

@router.post("/import-discovered")
async def import_discovered_leads(payload: ImportDiscoveredRequest):
    """
    Imports selected discovered Instagram & web prospects into the CRM,
    preserving verified profiles, observed opportunities, fit score breakdown,
    and personalized outreach drafts for human-reviewed outreach.
    """
    imported_leads = []
    skipped = 0

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_settings WHERE key = 'business_profile'")
        prof_row = cursor.fetchone()
        agency_profile = json.loads(prof_row["value"]) if prof_row else {}

    for item in payload.items:
        now = datetime.now().isoformat()
        lead_id = None

        with get_db() as conn:
            cursor = conn.cursor()
            dup = check_duplicate_lead(
                cursor,
                business_name=item.business_name,
                website_url=item.website_url or "",
                instagram_url=item.instagram_url or item.instagram_handle or ""
            )
            if dup:
                skipped += 1
                continue

            cursor.execute("""
                INSERT INTO leads (
                    business_name, industry, state, city, source_url, instagram_url, instagram_handle,
                    website_url, website_status, evidence_json, observed_problems, suggested_service,
                    opportunity, recommended_service, lead_score, confidence, score_breakdown_json,
                    personalized_dm, reasoning_summary, next_best_action, contact_name, public_phone,
                    public_email, outreach_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'high', ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?)
            """, (
                item.business_name.strip(),
                item.industry.strip(),
                item.state.strip(),
                item.city.strip() if item.city else "",
                item.source_url.strip(),
                item.instagram_url.strip(),
                item.instagram_handle.strip() if item.instagram_handle else "",
                item.website_url.strip(),
                item.website_status or "uncertain",
                json.dumps({
                    "snippet": item.snippet,
                    "contact": item.contact_details,
                    "score_reasons": item.score_reasons,
                    "discovered_at": item.discovered_at or now
                }),
                item.observed_problems or "",
                item.suggested_service or "",
                item.observed_problems or "",
                item.suggested_service or "",
                item.lead_score or 50,
                json.dumps(item.score_breakdown or {}),
                item.personalized_dm or "",
                f"Discovered via {item.provider_source or 'Instagram Prospect Discovery'}. Opportunity: {item.observed_problems}",
                "Review personalized DM draft and open verified Instagram profile to initiate human-reviewed contact",
                item.contact_details if not (item.public_phone or item.public_email) else "",
                item.public_phone or "",
                item.public_email or "",
                now, now
            ))
            lead_id = cursor.lastrowid
            conn.commit()

        # If website_url is provided, perform live website check
        web_evidence = {}
        web_status = item.website_status or "uncertain"
        if item.website_url:
            try:
                check_res = await check_website(item.website_url)
                web_status = check_res.status
                web_evidence = check_res.model_dump()
                with get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE leads SET
                            website_status = ?,
                            evidence_json = ?,
                            updated_at = ?
                        WHERE id = ?
                    """, (
                        web_status,
                        json.dumps({
                            "snippet": item.snippet,
                            "contact": item.contact_details,
                            "score_reasons": item.score_reasons,
                            "website_check": web_evidence
                        }),
                        datetime.now().isoformat(),
                        lead_id
                    ))
                    conn.commit()
            except Exception:
                pass

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
            imported_leads.append(row_to_lead(cursor.fetchone()))

    return {
        "status": "success",
        "imported_count": len(imported_leads),
        "skipped_count": skipped,
        "leads": imported_leads
    }


@router.get("/{lead_id}/messaging-status", response_model=LeadMessagingStatusResponse)
def get_lead_messaging_status(lead_id: int):
    """
    Checks Meta messaging eligibility for a specific CRM lead under Meta's official Platform Policy:
    - Verifies whether an active inbound conversation thread exists.
    - Cold first-contact DMs are strictly prohibited by Meta Graph API.
    - If eligible, provides conversation context and permits dashboard sending.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
        lead_row = cursor.fetchone()
        if not lead_row:
            raise HTTPException(status_code=404, detail="Lead not found")
        lead = dict(lead_row)

        conv_id = lead.get("conversation_id")
        conv = None
        if conv_id:
            cursor.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,))
            conv = cursor.fetchone()

        if not conv:
            cursor.execute("SELECT * FROM conversations WHERE lead_id = ? ORDER BY id DESC LIMIT 1", (lead_id,))
            conv = cursor.fetchone()

        # Fallback search by handle or URL if conv_id was not explicitly linked yet
        if not conv:
            handle = (lead.get("instagram_handle") or "").strip().lstrip("@")
            if not handle and lead.get("instagram_url"):
                from backend.app.services.discovery_service import extract_instagram_handle
                handle = extract_instagram_handle(lead["instagram_url"])

            if handle:
                cursor.execute("""
                    SELECT * FROM conversations
                    WHERE external_thread_id = ? OR recipient_id = ? OR contact_display_name = ?
                    ORDER BY id DESC LIMIT 1
                """, (handle, handle, handle))
                conv = cursor.fetchone()

        if conv:
            conv_id = conv["id"]
            cursor.execute("UPDATE leads SET conversation_id = ? WHERE id = ?", (conv_id, lead_id))
            cursor.execute("UPDATE conversations SET lead_id = ? WHERE id = ?", (lead_id, conv_id))
            conn.commit()

        meta_token_set = bool(settings.effective_instagram_token)

        if not conv:
            return LeadMessagingStatusResponse(
                eligible=False,
                can_send=False,
                conversation_id=None,
                recipient_id="",
                platform="manual",
                within_messaging_window=False,
                meta_connected=meta_token_set,
                reason="First-contact restriction: This prospect has not initiated an inbound conversation with @abenzo.co.in. Under Meta's Platform Policy, businesses cannot initiate unsolicited cold outbound DMs via API. Please use Copy Message and Open Profile to conduct authorized manual outreach directly on Instagram.",
                suggested_action="manual_outreach",
                outreach_status=lead.get("outreach_status", "new"),
                draft_message=lead.get("personalized_dm", "")
            )

        conv_dict = dict(conv)
        platform = conv_dict.get("platform", "manual")
        recipient_id = conv_dict.get("recipient_id") or conv_dict.get("external_thread_id") or ""
        last_msg_at = conv_dict.get("last_message_at")

        within_window = True
        if platform == "instagram" and last_msg_at:
            try:
                last_dt = datetime.fromisoformat(last_msg_at.replace("Z", "+00:00"))
                if last_dt.tzinfo is not None:
                    last_dt = last_dt.replace(tzinfo=None)
                diff_hours = (datetime.now() - last_dt).total_seconds() / 3600
                if diff_hours > 24:
                    within_window = False
            except Exception:
                within_window = True

        can_send = True
        reason = "Eligible: An active conversation exists. You may edit and send this message directly from the dashboard."
        if platform == "instagram" and not within_window:
            can_send = False
            reason = "Messaging window expired: Meta allows outbound messages within 24 hours of the user's last message. The 24-hour window for this conversation has closed."
        elif platform == "instagram" and not meta_token_set:
            can_send = False
            reason = "Instagram API token is not configured in backend environment."

        return LeadMessagingStatusResponse(
            eligible=True,
            can_send=can_send,
            conversation_id=conv_id,
            recipient_id=recipient_id,
            platform=platform,
            within_messaging_window=within_window,
            meta_connected=meta_token_set,
            reason=reason,
            suggested_action="dashboard_send" if can_send else "manual_outreach",
            outreach_status=lead.get("outreach_status", "new"),
            draft_message=lead.get("personalized_dm", "")
        )


@router.post("/{lead_id}/send-message", response_model=LeadSendMessageResponse)
async def send_lead_message(lead_id: int, payload: LeadSendMessageRequest):
    """
    Dispatches a message draft to an eligible lead from the dashboard:
    - Enforces Meta's Platform Policy: rejects cold first-contact DMs with clear guidance.
    - Prevents duplicate sends on repeated clicks.
    - Records outbound message in conversation history and updates CRM outreach_status to 'contacted' only upon confirmed delivery.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
        lead_row = cursor.fetchone()
        if not lead_row:
            raise HTTPException(status_code=404, detail="Lead not found")
        lead = dict(lead_row)

        conv_id = lead.get("conversation_id")
        conv = None
        if conv_id:
            cursor.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,))
            conv = cursor.fetchone()

        if not conv:
            cursor.execute("SELECT * FROM conversations WHERE lead_id = ? ORDER BY id DESC LIMIT 1", (lead_id,))
            conv = cursor.fetchone()

        if not conv:
            handle = (lead.get("instagram_handle") or "").strip().lstrip("@")
            if not handle and lead.get("instagram_url"):
                from backend.app.services.discovery_service import extract_instagram_handle
                handle = extract_instagram_handle(lead["instagram_url"])

            if handle:
                cursor.execute("""
                    SELECT * FROM conversations
                    WHERE external_thread_id = ? OR recipient_id = ? OR contact_display_name = ?
                    ORDER BY id DESC LIMIT 1
                """, (handle, handle, handle))
                conv = cursor.fetchone()

        if conv:
            conv_id = conv["id"]
            cursor.execute("UPDATE leads SET conversation_id = ? WHERE id = ?", (conv_id, lead_id))
            cursor.execute("UPDATE conversations SET lead_id = ? WHERE id = ?", (lead_id, conv_id))
            conn.commit()

        if not conv:
            raise HTTPException(
                status_code=403,
                detail="Unauthorized: Under Meta's official Platform Policy, automated or dashboard cold DMs cannot be sent to Instagram users who have never messaged your business. Use Copy Message and Open Profile to conduct authorized manual outreach on Instagram."
            )

        conv_dict = dict(conv)
        platform = conv_dict.get("platform", "manual")
        recipient_id = conv_dict.get("recipient_id") or conv_dict.get("external_thread_id") or ""

        text_to_send = (payload.message_text or lead.get("personalized_dm") or "").strip()
        if not text_to_send:
            raise HTTPException(status_code=400, detail="Message text cannot be empty.")

        # Duplicate send prevention: check if identical message was sent in last 60 seconds
        cursor.execute("""
            SELECT id, delivery_status, created_at FROM conversation_events
            WHERE conversation_id = ? AND direction = 'outbound' AND message_text = ?
            ORDER BY id DESC LIMIT 1
        """, (conv_id, text_to_send))
        recent_event = cursor.fetchone()
        if recent_event and recent_event["delivery_status"] in ("sending", "sent"):
            is_recent_dup = False
            try:
                ev_time = datetime.fromisoformat(recent_event["created_at"])
                if (datetime.now() - ev_time).total_seconds() < 60:
                    is_recent_dup = True
            except Exception:
                is_recent_dup = True

            if is_recent_dup:
                raise HTTPException(
                    status_code=409,
                    detail="Duplicate message send prevented: An identical message is currently in-flight or was sent within the last minute."
                )

        now_str = datetime.now().isoformat()

        # Handle sample / manual test conversations
        if platform in ("instagram_sample", "manual") or recipient_id.startswith("sample_") or recipient_id.startswith("manual_"):
            cursor.execute("""
                INSERT INTO conversation_events (
                    conversation_id, external_event_id, event_type, direction,
                    message_text, approved_text, delivery_status, meta_message_id, sent_at, created_at
                ) VALUES (?, ?, 'dm', 'outbound', ?, ?, 'sent', 'sample_dashboard_sent', ?, ?)
            """, (conv_id, f"sample_lead_{uuid.uuid4().hex[:10]}", text_to_send, text_to_send, now_str, now_str))
            event_id = cursor.lastrowid

            cursor.execute("""
                UPDATE leads SET
                    outreach_status = 'contacted',
                    outreach_action_at = ?,
                    updated_at = ?
                WHERE id = ?
            """, (now_str, now_str, lead_id))

            cursor.execute("""
                UPDATE conversations SET
                    last_message_at = ?,
                    needs_human = 0,
                    updated_at = ?
                WHERE id = ?
            """, (now_str, now_str, conv_id))
            conn.commit()

            return LeadSendMessageResponse(
                status="sent",
                delivery_status="sent",
                meta_message_id="sample_dashboard_sent",
                event_id=event_id,
                conversation_id=conv_id,
                lead_id=lead_id,
                sent_at=now_str,
                error_details=""
            )

        # Real Instagram conversation verification
        if platform != "instagram":
            raise HTTPException(
                status_code=400,
                detail=f"Outbound delivery only supported for Instagram conversations (current: '{platform}')."
            )

        if not recipient_id or recipient_id in ("29266079986333250", "17841428389805643"):
            raise HTTPException(
                status_code=400,
                detail="Invalid recipient ID: Inbound conversation does not have a verified Instagram user ID."
            )

        # Create outbound event in 'sending' state
        cursor.execute("""
            INSERT INTO conversation_events (
                conversation_id, external_event_id, event_type, direction,
                message_text, approved_text, delivery_status, created_at
            ) VALUES (?, ?, 'dm', 'outbound', ?, ?, 'sending', ?)
        """, (conv_id, f"out_lead_{uuid.uuid4().hex[:12]}", text_to_send, text_to_send, now_str))
        event_id = cursor.lastrowid
        conn.commit()

    # Dispatch via Meta Graph API
    from backend.app.routers.meta import dispatch_instagram_dm
    dispatch_res = await dispatch_instagram_dm(recipient_id, text_to_send)

    with get_db() as conn:
        cursor = conn.cursor()
        now_str = datetime.now().isoformat()

        if dispatch_res.get("success"):
            meta_mid = dispatch_res.get("meta_message_id") or dispatch_res.get("message_id") or ""
            cursor.execute("""
                UPDATE conversation_events SET
                    delivery_status = 'sent',
                    meta_message_id = ?,
                    sent_at = ?,
                    error_details = ''
                WHERE id = ?
            """, (meta_mid, now_str, event_id))

            cursor.execute("""
                UPDATE leads SET
                    outreach_status = 'contacted',
                    outreach_action_at = ?,
                    updated_at = ?
                WHERE id = ?
            """, (now_str, now_str, lead_id))

            cursor.execute("""
                UPDATE conversations SET
                    last_message_at = ?,
                    needs_human = 0,
                    updated_at = ?
                WHERE id = ?
            """, (now_str, now_str, conv_id))
            conn.commit()

            return LeadSendMessageResponse(
                status="sent",
                delivery_status="sent",
                meta_message_id=meta_mid,
                event_id=event_id,
                conversation_id=conv_id,
                lead_id=lead_id,
                sent_at=now_str,
                error_details=""
            )
        else:
            err_details = dispatch_res.get("error_details", "Meta Graph API dispatch failed.")
            cursor.execute("""
                UPDATE conversation_events SET
                    delivery_status = 'failed',
                    error_details = ?
                WHERE id = ?
            """, (err_details, event_id))
            conn.commit()

            raise HTTPException(
                status_code=502,
                detail=f"Message delivery failed: {err_details}"
            )


@router.post("/{lead_id}/recalculate-qualification", response_model=LeadResponse)
async def recalculate_lead_qualification(lead_id: int):
    """
    Safely re-evaluates website verification and opportunity scoring for an existing lead:
    - Never overwrites custom operator notes or customer data.
    - Accurately checks website availability, SSL, and features if website_url is present.
    - Removes arbitrary no-website bonuses in favor of evidence-based scoring.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Lead not found")
        lead = row_to_lead(row)

    web_url = lead.get("website_url", "").strip()
    evidence = lead.get("evidence_json", {})
    web_check_data = {}

    if web_url:
        check_res = await check_website(web_url)
        web_check_data = check_res.model_dump()
        status = check_res.status
    else:
        # Check if bio snippet explicitly indicates direct DM ordering
        snippet = lead.get("source_caption", "") or lead.get("business_summary", "")
        if any(w in snippet.lower() for w in ["dm to order", "order via dm", "no website"]):
            status = "no_website"
        else:
            status = "uncertain"

    # Evaluate digital opportunity
    opp_data = evaluate_digital_opportunity(
        business_name=lead["business_name"],
        niche=lead.get("industry", "Local Business"),
        city=lead.get("city", ""),
        website_url=web_url,
        instagram_handle=lead.get("instagram_handle", ""),
        snippet=lead.get("source_caption", "") or lead.get("business_summary", ""),
        contacts={
            "phones": [lead["public_phone"]] if lead.get("public_phone") else [],
            "emails": [lead["public_email"]] if lead.get("public_email") else [],
            "external_links": [web_url] if web_url else []
        }
    )

    evidence["website_check"] = web_check_data
    evidence["recalculated_at"] = datetime.now().isoformat()
    now = datetime.now().isoformat()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE leads SET
                website_status = ?,
                lead_score = ?,
                observed_problems = ?,
                opportunity = ?,
                suggested_service = ?,
                score_breakdown_json = ?,
                evidence_json = ?,
                updated_at = ?
            WHERE id = ?
        """, (
            opp_data["website_status"],
            opp_data["lead_score"],
            opp_data["observed_problems"],
            opp_data["opportunity"],
            opp_data["suggested_service"],
            json.dumps(opp_data["score_breakdown"]),
            json.dumps(evidence),
            now,
            lead_id
        ))
        conn.commit()

        cursor.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
        return row_to_lead(cursor.fetchone())
