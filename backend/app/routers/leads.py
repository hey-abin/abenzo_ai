import json
import csv
import io
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Response
from typing import Optional, List
from backend.app.database import get_db
from backend.app.schemas import (
    LeadCreate,
    LeadUpdate,
    LeadResponse,
    LeadDiscoveryQuery,
    LeadDiscoveryResponse,
    ImportDiscoveredRequest
)
from backend.app.services.website_checker import check_website
from backend.app.services.ollama_service import qualify_lead_with_ai
from backend.app.services.discovery_service import check_duplicate_lead, execute_lead_discovery

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
        "consent_source", "follow_up_date", "outreach_action_at"
    ):
        if d.get(key) is None:
            d[key] = ""
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
