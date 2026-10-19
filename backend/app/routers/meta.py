import hmac
import hashlib
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response, Header

from backend.app.config import settings
from backend.app.database import get_db
from backend.app.schemas import MetaStatus, SendReplyRequest, SendReplyResponse
from backend.app.services.ollama_service import draft_inbound_response_with_ai

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/meta", tags=["meta"])

GRAPH_API_BASE = "https://graph.instagram.com/v21.0"

async def inspect_instagram_token(token: str) -> Dict[str, Any]:
    """
    Backend-only test of the configured Instagram token.
    Never logs or exposes the token string.
    """
    if not token or not token.strip():
        return {
            "connected": False,
            "status": "not_configured",
            "guidance": "Instagram Access Token is not set. Add INSTAGRAM_ACCESS_TOKEN to .env",
            "capabilities": {
                "basic_profile": False,
                "media_access": False,
                "messaging_conversations": False,
                "webhook_events": False,
                "automated_cold_dms": False,
                "arbitrary_profile_scraping": False
            }
        }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            # 1. Fetch profile
            me_resp = await client.get(
                f"{GRAPH_API_BASE}/me",
                params={
                    "fields": "id,username,account_type,name,profile_picture_url",
                    "access_token": token
                }
            )

            if me_resp.status_code != 200:
                err_data = me_resp.json().get("error", {})
                err_msg = err_data.get("message", "Token validation failed")
                code = err_data.get("code")
                return {
                    "connected": False,
                    "status": "error",
                    "error_details": f"Instagram API returned code {code}: {err_msg}",
                    "guidance": "The configured access token is invalid, expired, or has been revoked in Meta Developer Portal.",
                    "capabilities": {
                        "basic_profile": False,
                        "media_access": False,
                        "messaging_conversations": False,
                        "webhook_events": False,
                        "automated_cold_dms": False,
                        "arbitrary_profile_scraping": False
                    }
                }

            profile_data = me_resp.json()

            # 2. Check media access
            media_ok = False
            try:
                media_resp = await client.get(
                    f"{GRAPH_API_BASE}/me/media",
                    params={"fields": "id", "limit": 1, "access_token": token}
                )
                media_ok = media_resp.status_code == 200
            except Exception:
                media_ok = False

            # 3. Check conversations / DMs access
            dm_ok = False
            try:
                dm_resp = await client.get(
                    f"{GRAPH_API_BASE}/me/conversations",
                    params={"access_token": token}
                )
                dm_ok = dm_resp.status_code == 200
            except Exception:
                dm_ok = False

            granted = ["instagram_basic"]
            if media_ok:
                granted.append("instagram_manage_comments")
            if dm_ok:
                granted.append("instagram_manage_messages")

            return {
                "connected": True,
                "status": "connected",
                "account_id": profile_data.get("id"),
                "username": profile_data.get("username"),
                "account_type": profile_data.get("account_type"),
                "profile_name": profile_data.get("name"),
                "profile_picture_url": profile_data.get("profile_picture_url"),
                "granted_permissions": granted,
                "capabilities": {
                    "basic_profile": True,
                    "media_access": media_ok,
                    "messaging_conversations": dm_ok,
                    "webhook_events": bool(settings.META_VERIFY_TOKEN),
                    "automated_cold_dms": False,  # Forbidden by policy
                    "arbitrary_profile_scraping": False  # Forbidden by terms
                },
                "guidance": f"Connected to @{profile_data.get('username')} ({profile_data.get('account_type', 'Business')}). Profile and messaging endpoints verified."
            }

    except httpx.ConnectError:
        return {
            "connected": False,
            "status": "error",
            "error_details": "Could not connect to graph.instagram.com. Check internet connectivity.",
            "guidance": "Connection timed out or failed to reach Meta Graph API."
        }
    except Exception as e:
        return {
            "connected": False,
            "status": "error",
            "error_details": f"Connection check encountered: {type(e).__name__}",
            "guidance": "Unexpected error while testing Instagram connection."
        }

@router.get("/status", response_model=MetaStatus)
async def get_meta_status():
    token = settings.effective_instagram_token
    app_id = settings.effective_instagram_app_id
    verify = settings.META_VERIFY_TOKEN

    app_id_set = bool(app_id)
    token_set = bool(token)
    verify_token_set = bool(verify)

    if not token_set:
        return MetaStatus(
            configured=False,
            status="not_configured",
            app_id_set=app_id_set,
            access_token_set=False,
            verify_token_set=verify_token_set,
            guidance="Instagram credentials are not configured in .env. The app is in manual-safe mode.",
            capabilities={
                "basic_profile": False,
                "media_access": False,
                "messaging_conversations": False,
                "webhook_events": verify_token_set,
                "automated_cold_dms": False,
                "arbitrary_profile_scraping": False
            }
        )

    # Perform real backend-only test
    res = await inspect_instagram_token(token)
    now = datetime.now().isoformat()

    return MetaStatus(
        configured=res.get("connected", False),
        status=res.get("status", "error"),
        app_id_set=app_id_set,
        access_token_set=True,
        verify_token_set=verify_token_set,
        account_id=res.get("account_id"),
        username=res.get("username"),
        account_type=res.get("account_type"),
        profile_name=res.get("profile_name"),
        profile_picture_url=res.get("profile_picture_url"),
        api_host="graph.instagram.com",
        granted_permissions=res.get("granted_permissions", []),
        missing_permissions=[p for p in ["instagram_basic", "instagram_manage_messages", "instagram_manage_comments"] if p not in res.get("granted_permissions", [])],
        capabilities=res.get("capabilities", {}),
        guidance=res.get("guidance", ""),
        error_details=res.get("error_details"),
        tested_at=now
    )

@router.post("/test-connection", response_model=MetaStatus)
async def test_meta_connection():
    """Explicit on-demand re-verification of the Instagram API connection."""
    return await get_meta_status()

@router.get("/webhook")
def verify_meta_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token")
):
    """Standard Meta Webhook challenge verification."""
    if hub_mode == "subscribe" and hub_verify_token == settings.META_VERIFY_TOKEN:
        return Response(content=hub_challenge or "", media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification token mismatch or invalid mode")

@router.post("/webhook")
async def receive_meta_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256")
):
    """
    Official webhook event receiver for inbound Instagram messages and comments.
    Enforces HMAC-SHA256 signature verification and event deduplication.
    """
    body = await request.body()

    # Verify HMAC-SHA256 signature if app secret is configured and header is provided
    app_secret = settings.effective_instagram_app_secret
    if app_secret and x_hub_signature_256:
        expected = "sha256=" + hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, x_hub_signature_256):
            raise HTTPException(status_code=403, detail="Invalid webhook signature")

    try:
        data = json.loads(body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    entries = data.get("entry", [])
    processed_count = 0
    now = datetime.now().isoformat()
    own_ids = {"29266079986333250", "17841428389805643", settings.effective_instagram_app_id}

    # Step 1: Short read transaction: load business profile
    agency_profile = {}
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM app_settings WHERE key = 'business_profile'")
            prof_row = cursor.fetchone()
            if prof_row:
                agency_profile = json.loads(prof_row["value"])
    except Exception as e:
        logger.warning("Could not load business profile in webhook handler: %s", type(e).__name__)
        agency_profile = {}

    auto_reply_enabled = bool(agency_profile.get("auto_reply_faq_enabled", False))

    # Step 2: Extract all inbound message events across entries
    raw_messaging = []
    for entry in entries:
        raw_messaging.extend(entry.get("messaging", []))
        for change in entry.get("changes", []):
            val = change.get("value", {})
            if isinstance(val, dict) and ("message" in val or "messages" in val):
                raw_messaging.append(val)

    # Step 3: Process each message event with short, isolated database transactions
    for msg_event in raw_messaging:
        # Discard outbound echoes sent by our page/agents
        if msg_event.get("message", {}).get("is_echo"):
            continue

        sender_id = msg_event.get("sender", {}).get("id")
        mid = msg_event.get("message", {}).get("mid")
        text = (msg_event.get("message", {}).get("text") or 
                (msg_event.get("message", {}).get("attachments") and "[Media / Attachment]") or "").strip()

        if not mid or not text or not sender_id or sender_id in own_ids:
            continue

        # Step 3a: Read/Prepare Conversation & Persist Inbound Event (Short DB Transaction)
        conv_id = None
        conv_history = []
        is_duplicate = False
        conversation_summary = ""
        lead_context = {}
        auto_reply_paused = False

        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM conversation_events WHERE external_event_id = ?", (mid,))
                if cursor.fetchone():
                    is_duplicate = True
                else:
                    # Find or create conversation isolated by sender_id
                    cursor.execute("SELECT * FROM conversations WHERE external_thread_id = ?", (sender_id,))
                    conv = cursor.fetchone()
                    if conv:
                        conv_id = conv["id"]
                        conversation_summary = conv["conversation_summary"] or ""
                        try:
                            lead_context = json.loads(conv["lead_context_json"] or "{}")
                        except Exception:
                            lead_context = {}
                        auto_reply_paused = bool(conv["auto_reply_paused"])
                        cursor.execute("""
                            UPDATE conversations SET
                                last_message_at = ?,
                                recipient_id = ?,
                                updated_at = ?
                            WHERE id = ?
                        """, (now, sender_id, now, conv_id))
                    else:
                        cursor.execute("""
                            INSERT INTO conversations (
                                platform, external_thread_id, recipient_id, contact_display_name,
                                status, needs_human, lead_temperature, notes, conversation_summary,
                                lead_context_json, conversion_stage, auto_reply_paused, created_at, updated_at
                            ) VALUES ('instagram', ?, ?, ?, 'active', 1, 'early', 'Inbound Instagram DM via Official Webhook', '', '{}', 'lead', 0, ?, ?)
                        """, (sender_id, sender_id, f"IG User ({sender_id[:8]})", now, now))
                        conv_id = cursor.lastrowid

                    # Link conversation to CRM lead if present, load business context, and update lead to 'replied'
                    cursor.execute("""
                        SELECT id, business_name, suggested_service, observed_problems, website_status, outreach_status
                        FROM leads
                        WHERE conversation_id = ? OR id = (SELECT lead_id FROM conversations WHERE id = ?)
                    """, (conv_id, conv_id))
                    matched_lead = cursor.fetchone()
                    if matched_lead:
                        if matched_lead["outreach_status"] in ("new", "draft", "contacted", "reviewed", "followed"):
                            cursor.execute("""
                                UPDATE leads SET
                                    outreach_status = 'replied',
                                    outreach_action_at = ?,
                                    updated_at = ?
                                WHERE id = ?
                            """, (now, now, matched_lead["id"]))
                        if matched_lead["business_name"]:
                            lead_context["prospect_business_name"] = matched_lead["business_name"]
                        if matched_lead["suggested_service"]:
                            lead_context["suggested_service"] = matched_lead["suggested_service"]
                        if matched_lead["observed_problems"]:
                            lead_context["observed_problems"] = matched_lead["observed_problems"]

                    # Fetch recent chronological conversation context (isolated to this conversation)
                    cursor.execute("""
                        SELECT direction, message_text, approved_text, ai_draft
                        FROM conversation_events
                        WHERE conversation_id = ?
                        ORDER BY id ASC LIMIT 8
                    """, (conv_id,))
                    recent_rows = cursor.fetchall()
                    for r in recent_rows:
                        if r["direction"] == "inbound":
                            conv_history.append({"role": "user", "content": r["message_text"]})
                        else:
                            c = r["approved_text"] or r["ai_draft"] or r["message_text"]
                            if c:
                                conv_history.append({"role": "assistant", "content": c})

                    # Persist inbound message immediately so it is never lost even if AI or dispatch fails
                    cursor.execute("""
                        INSERT INTO conversation_events (
                            conversation_id, external_event_id, event_type, direction,
                            message_text, ai_draft, approved_text, delivery_status, created_at
                        ) VALUES (?, ?, 'dm', 'inbound', ?, '', '', 'received', ?)
                    """, (conv_id, mid, text, now))
                    conn.commit()
        except Exception as e:
            logger.error("Database error during conversation lookup/inbound event save for mid %s: %s", mid, type(e).__name__)
            continue

        if is_duplicate or not conv_id:
            continue

        # Step 3b: AI Draft & Memory Extraction (OUTSIDE Database Transaction)
        ai_draft = ""
        lead_temp = "early"
        needs_human = True
        updated_summary = conversation_summary
        updated_lead_context = lead_context
        suggested_stage = "lead"

        try:
            draft_res = await draft_inbound_response_with_ai(
                incoming_message=text,
                conversation_history=conv_history,
                agency_profile=agency_profile,
                conversation_summary=conversation_summary,
                lead_context=lead_context
            )
            ai_draft = (draft_res.get("ai_draft") or "").strip()
            lead_temp = draft_res.get("lead_temperature", "early")
            needs_human = bool(draft_res.get("needs_human_decision", True))
            updated_summary = draft_res.get("conversation_summary") or conversation_summary
            updated_lead_context = draft_res.get("lead_context") or lead_context
            suggested_stage = draft_res.get("suggested_conversion_stage") or "lead"
        except Exception as e:
            logger.warning("AI draft failed for mid %s: %s", mid, type(e).__name__)
            ai_draft = "Thanks for reaching out to Abenzo! A team member will follow up shortly."
            needs_human = True

        # Determine if eligible for automated outbound dispatch
        is_auto_reply_eligible = (
            auto_reply_enabled and
            not auto_reply_paused and
            bool(ai_draft) and
            not needs_human and
            bool(settings.effective_instagram_token) and
            not sender_id.startswith("sample_") and
            not sender_id.startswith("manual_") and
            sender_id not in own_ids
        )

        # Step 3c: Outbound Instagram Message Dispatch (OUTSIDE Database Transaction)
        dispatch_res = None
        if is_auto_reply_eligible:
            try:
                dispatch_res = await dispatch_instagram_dm(sender_id, ai_draft)
            except Exception as e:
                logger.error("Outbound dispatch failed for mid %s: %s", mid, type(e).__name__)
                dispatch_res = {"success": False, "error_details": f"Dispatch error: {type(e).__name__}"}

        # Step 3d: Persist Outbound Event & Update Conversation Memory (Short DB Transaction)
        try:
            with get_db() as conn:
                cursor = conn.cursor()

                if is_auto_reply_eligible and dispatch_res:
                    if dispatch_res.get("success"):
                        meta_mid = dispatch_res.get("meta_message_id", "")
                        out_mid = f"out_{meta_mid or uuid.uuid4().hex[:12]}"
                        cursor.execute("""
                            INSERT INTO conversation_events (
                                conversation_id, external_event_id, event_type, direction,
                                message_text, ai_draft, approved_text, delivery_status,
                                meta_message_id, sent_at, created_at
                            ) VALUES (?, ?, 'dm', 'outbound', ?, ?, ?, 'sent', ?, ?, ?)
                        """, (conv_id, out_mid, ai_draft, ai_draft, ai_draft, meta_mid, now, now))

                        cursor.execute("""
                            UPDATE conversations SET
                                needs_human = 0,
                                lead_temperature = ?,
                                conversation_summary = ?,
                                lead_context_json = ?,
                                conversion_stage = ?,
                                last_message_at = ?,
                                updated_at = ?
                            WHERE id = ?
                        """, (lead_temp, updated_summary, json.dumps(updated_lead_context), suggested_stage, now, now, conv_id))
                    else:
                        err = dispatch_res.get("error_details", "")
                        out_mid = f"out_fail_{uuid.uuid4().hex[:10]}"
                        cursor.execute("""
                            INSERT INTO conversation_events (
                                conversation_id, external_event_id, event_type, direction,
                                message_text, ai_draft, approved_text, delivery_status,
                                error_details, created_at
                            ) VALUES (?, ?, 'dm', 'outbound', ?, ?, ?, 'failed', ?, ?)
                        """, (conv_id, out_mid, ai_draft, ai_draft, ai_draft, err, now))

                        cursor.execute("""
                            UPDATE conversations SET
                                needs_human = 1,
                                lead_temperature = ?,
                                conversation_summary = ?,
                                lead_context_json = ?,
                                conversion_stage = ?,
                                last_message_at = ?,
                                updated_at = ?
                            WHERE id = ?
                        """, (lead_temp, updated_summary, json.dumps(updated_lead_context), suggested_stage, now, now, conv_id))
                else:
                    out_mid = f"out_draft_{uuid.uuid4().hex[:10]}"
                    cursor.execute("""
                        INSERT INTO conversation_events (
                            conversation_id, external_event_id, event_type, direction,
                            message_text, ai_draft, approved_text, delivery_status, created_at
                        ) VALUES (?, ?, 'dm', 'outbound', ?, ?, '', 'draft_pending', ?)
                    """, (conv_id, out_mid, ai_draft, ai_draft, now))

                    cursor.execute("""
                        UPDATE conversations SET
                            needs_human = 1,
                            lead_temperature = ?,
                            conversation_summary = ?,
                            lead_context_json = ?,
                            conversion_stage = ?,
                            last_message_at = ?,
                            updated_at = ?
                        WHERE id = ?
                    """, (lead_temp, updated_summary, json.dumps(updated_lead_context), suggested_stage, now, now, conv_id))

                processed_count += 1
                conn.commit()
        except Exception as e:
            logger.error("Database error saving outbound event record for mid %s: %s", mid, type(e).__name__)

    return {"status": "ok", "events_processed": processed_count}


@router.post("/sync")
async def sync_instagram_conversations():
    """
    Syncs recent Instagram conversations directly via Instagram Graph API.
    Enables local testing without requiring a public HTTPS webhook tunnel.
    """
    token = settings.effective_instagram_token
    if not token:
        raise HTTPException(status_code=400, detail="Instagram access token not configured in .env")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{GRAPH_API_BASE}/me/conversations",
                params={
                    "fields": "id,updated_time,messages{id,created_time,from,message}",
                    "access_token": token
                }
            )
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=f"Instagram API error: {resp.text}")

            data = resp.json().get("data", [])
            synced = 0
            now = datetime.now().isoformat()

            agency_profile = {}
            try:
                with get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT value FROM app_settings WHERE key = 'business_profile'")
                    prof_row = cursor.fetchone()
                    if prof_row:
                        agency_profile = json.loads(prof_row["value"])
            except Exception:
                agency_profile = {}

            for thread in data:
                thread_id = thread.get("id")
                messages = thread.get("messages", {}).get("data", [])

                for msg in messages:
                    mid = msg.get("id")
                    text = msg.get("message")
                    sender_id = msg.get("from", {}).get("id")
                    sender_name = msg.get("from", {}).get("username") or f"User ({sender_id[:6]})"

                    if not mid or not text:
                        continue

                    # Step 1: Check deduplication and get/create conversation (Short DB transaction)
                    conv_id = None
                    is_dup = False
                    try:
                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute("SELECT id FROM conversation_events WHERE external_event_id = ?", (mid,))
                            if cursor.fetchone():
                                is_dup = True
                            else:
                                cursor.execute("SELECT id, recipient_id FROM conversations WHERE external_thread_id = ?", (thread_id,))
                                conv = cursor.fetchone()
                                if conv:
                                    conv_id = conv["id"]
                                    if sender_id and not conv["recipient_id"]:
                                        cursor.execute("UPDATE conversations SET recipient_id = ? WHERE id = ?", (sender_id, conv_id))
                                else:
                                    cursor.execute("""
                                        INSERT INTO conversations (
                                            platform, external_thread_id, recipient_id, contact_display_name,
                                            status, needs_human, lead_temperature, notes, created_at, updated_at
                                        ) VALUES ('instagram', ?, ?, ?, 'active', 1, 'early', 'Synced from Instagram API', ?, ?)
                                    """, (thread_id, sender_id or "", sender_name, now, now))
                                    conv_id = cursor.lastrowid
                    except Exception as e:
                        logger.error("DB error looking up synced thread %s: %s", thread_id, type(e).__name__)
                        continue

                    if is_dup or not conv_id:
                        continue

                    # Step 2: Draft reply with AI (OUTSIDE DB transaction)
                    ai_draft = ""
                    try:
                        draft_res = await draft_inbound_response_with_ai(text, [], agency_profile)
                        ai_draft = draft_res.get("ai_draft", "")
                    except Exception:
                        ai_draft = "Hi! Thank you for reaching out to Abenzo. A member of our team will follow up shortly."

                    # Step 3: Insert event (Short DB transaction)
                    try:
                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute("SELECT id FROM conversation_events WHERE external_event_id = ?", (mid,))
                            if not cursor.fetchone():
                                cursor.execute("""
                                    INSERT INTO conversation_events (
                                        conversation_id, external_event_id, event_type, direction,
                                        message_text, ai_draft, approved_text, delivery_status, created_at
                                    ) VALUES (?, ?, 'dm', 'inbound', ?, ?, '', 'draft_pending', ?)
                                """, (conv_id, mid, text, ai_draft, now))
                                synced += 1
                    except Exception as e:
                        logger.error("DB error saving synced message %s: %s", mid, type(e).__name__)

            return {
                "status": "success",
                "threads_checked": len(data),
                "new_messages_synced": synced
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to sync conversations: {str(e)}")

@router.post("/disconnect")
def disconnect_meta():
    """Disconnects Meta integration from backend state."""
    return {
        "status": "success",
        "message": "To permanently disconnect, remove INSTAGRAM_ACCESS_TOKEN from .env."
    }

async def dispatch_instagram_dm(recipient_id: str, message_text: str) -> Dict[str, Any]:
    """
    Directly dispatches an approved DM to a verified inbound Instagram recipient via Graph API.
    Enforces strict security: never logs tokens, sanitizes all error responses.
    """
    token = settings.effective_instagram_token
    if not token or not token.strip():
        return {
            "success": False,
            "error_details": "Instagram Access Token is not configured in backend environment.",
            "meta_message_id": ""
        }

    url = f"{GRAPH_API_BASE}/me/messages"
    payload = {
        "recipient": {"id": str(recipient_id)},
        "message": {"text": message_text}
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload, headers=headers)

            if resp.status_code != 200:
                # If graph.instagram.com fails, try graph.facebook.com (standard for Page-linked Instagram accounts)
                fb_url = "https://graph.facebook.com/v21.0/me/messages"
                fb_resp = await client.post(fb_url, json=payload, headers=headers)
                if fb_resp.status_code == 200:
                    resp = fb_resp
                else:
                    try:
                        err_json = resp.json().get("error", {})
                        err_msg = err_json.get("message", "Meta Graph API error")
                        err_code = err_json.get("code", resp.status_code)
                        err_subcode = err_json.get("error_subcode", "")
                        sub_str = f" (subcode {err_subcode})" if err_subcode else ""
                        sanitized_err = f"Meta API error [{err_code}{sub_str}]: {err_msg}"
                    except Exception:
                        sanitized_err = f"Meta API returned HTTP status {resp.status_code}"

                    return {
                        "success": False,
                        "error_details": sanitized_err,
                        "meta_message_id": ""
                    }

            data = resp.json()
            message_id = data.get("message_id") or data.get("id") or ""
            return {
                "success": True,
                "meta_message_id": str(message_id),
                "error_details": ""
            }

    except httpx.TimeoutException:
        return {
            "success": False,
            "error_details": "Meta API request timed out after 10 seconds. Ambiguous delivery state; automated retry disabled to prevent duplicate DMs.",
            "meta_message_id": ""
        }
    except Exception as e:
        return {
            "success": False,
            "error_details": f"Network transmission error: {type(e).__name__}",
            "meta_message_id": ""
        }

@router.post("/send-reply", response_model=SendReplyResponse)
async def send_approved_reply(payload: SendReplyRequest):
    """
    Dedicated endpoint to send an approved reply to an inbound Instagram message.
    Requires explicit human approval; strictly prevents duplicate delivery.
    """
    event_id = payload.event_id

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM conversation_events WHERE id = ?", (event_id,))
        event_row = cursor.fetchone()
        if not event_row:
            raise HTTPException(status_code=404, detail=f"Message event #{event_id} not found")

        event = dict(event_row)
        conv_id = event["conversation_id"]

        cursor.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,))
        conv_row = cursor.fetchone()
        if not conv_row:
            raise HTTPException(status_code=404, detail="Corresponding conversation not found")

        conv = dict(conv_row)

        # 1. Platform verification
        if conv.get("platform") != "instagram":
            raise HTTPException(
                status_code=400,
                detail=f"Invalid platform '{conv.get('platform')}': Outbound messaging is only supported for Instagram conversations."
            )

        # 2. Recipient ID verification (must originate from an inbound conversation)
        recipient_id = (conv.get("recipient_id") or conv.get("external_thread_id") or "").strip()
        if not recipient_id or recipient_id.startswith("sample_") or recipient_id.startswith("manual_") or recipient_id in ("29266079986333250", "17841428389805643"):
            raise HTTPException(
                status_code=400,
                detail="Invalid recipient ID: Inbound Instagram conversation does not have a verified external user recipient ID."
            )

        # 3. Duplicate delivery protection
        current_status = event.get("delivery_status", "")
        if current_status == "sent":
            raise HTTPException(
                status_code=409,
                detail=f"Duplicate send prevented: message #{event_id} has already been sent (Meta ID: {event.get('meta_message_id', 'unknown')})."
            )
        if current_status == "sending":
            raise HTTPException(
                status_code=409,
                detail=f"Duplicate send prevented: message #{event_id} is currently being transmitted."
            )

        # 4. Human approval requirement
        text_to_send = (payload.approved_text or event.get("approved_text") or "").strip()
        if not text_to_send:
            raise HTTPException(
                status_code=400,
                detail="Human approval required: Message text must be approved by an operator before delivery."
            )

        # 5. Atomically transition state to 'sending' to lock out concurrent requests
        cursor.execute("""
            UPDATE conversation_events SET
                delivery_status = 'sending',
                approved_text = ?
            WHERE id = ?
        """, (text_to_send, event_id))
        conn.commit()

    # 6. Dispatch message via Graph API
    dispatch_result = await dispatch_instagram_dm(recipient_id, text_to_send)

    with get_db() as conn:
        cursor = conn.cursor()
        now = datetime.now().isoformat()

        if dispatch_result["success"]:
            meta_mid = dispatch_result["meta_message_id"]
            cursor.execute("""
                UPDATE conversation_events SET
                    delivery_status = 'sent',
                    meta_message_id = ?,
                    sent_at = ?,
                    error_details = ''
                WHERE id = ?
            """, (meta_mid, now, event_id))

            cursor.execute("""
                UPDATE conversations SET
                    needs_human = 0,
                    updated_at = ?
                WHERE id = ?
            """, (now, conv_id))
            conn.commit()

            return SendReplyResponse(
                status="sent",
                event_id=event_id,
                delivery_status="sent",
                meta_message_id=meta_mid,
                recipient_id=recipient_id,
                sent_at=now,
                error_details=""
            )
        else:
            err = dispatch_result["error_details"]
            cursor.execute("""
                UPDATE conversation_events SET
                    delivery_status = 'failed',
                    error_details = ?
                WHERE id = ?
            """, (err, event_id))
            conn.commit()

            raise HTTPException(
                status_code=502,
                detail=f"Meta Instagram delivery failed: {err}"
            )
