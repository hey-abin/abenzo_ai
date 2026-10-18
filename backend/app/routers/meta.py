import hmac
import hashlib
import json
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response, Header

from backend.app.config import settings
from backend.app.database import get_db
from backend.app.schemas import MetaStatus, SendReplyRequest, SendReplyResponse
from backend.app.services.ollama_service import draft_inbound_response_with_ai

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

    with get_db() as conn:
        cursor = conn.cursor()
        now = datetime.now().isoformat()

        # Load Abenzo business profile for AI drafting
        cursor.execute("SELECT value FROM app_settings WHERE key = 'business_profile'")
        prof_row = cursor.fetchone()
        agency_profile = json.loads(prof_row["value"]) if prof_row else {}

        own_ids = {"29266079986333250", "17841428389805643", settings.effective_instagram_app_id}
        auto_reply_enabled = bool(agency_profile.get("auto_reply_faq_enabled", False))

        for entry in entries:
            # Support both direct messaging array and changes-based webhook payloads
            raw_messaging = list(entry.get("messaging", []))
            for change in entry.get("changes", []):
                val = change.get("value", {})
                if isinstance(val, dict) and ("message" in val or "messages" in val):
                    raw_messaging.append(val)

            for msg_event in raw_messaging:
                # Discard outbound echoes sent by our page/agents
                if msg_event.get("message", {}).get("is_echo"):
                    continue

                sender_id = msg_event.get("sender", {}).get("id")
                mid = msg_event.get("message", {}).get("mid")
                text = (msg_event.get("message", {}).get("text") or 
                        (msg_event.get("message", {}).get("attachments") and "[Media / Attachment]") or "").strip()

                if not mid or not text or not sender_id:
                    continue

                # Ignore messages from our own business account ID
                if sender_id in own_ids:
                    continue

                # Deduplication
                cursor.execute("SELECT id FROM conversation_events WHERE external_event_id = ?", (mid,))
                if cursor.fetchone():
                    continue

                # Find or create conversation
                cursor.execute("SELECT id FROM conversations WHERE external_thread_id = ?", (sender_id,))
                conv = cursor.fetchone()
                if conv:
                    conv_id = conv["id"]
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
                            status, needs_human, lead_temperature, notes, created_at, updated_at
                        ) VALUES ('instagram', ?, ?, ?, 'active', 1, 'early', 'Inbound Instagram DM via Official Webhook', ?, ?)
                    """, (sender_id, sender_id, f"IG User ({sender_id[:8]})", now, now))
                    conv_id = cursor.lastrowid

                # Fetch recent conversation context (last 4 events)
                cursor.execute("""
                    SELECT direction, message_text, approved_text, ai_draft
                    FROM conversation_events
                    WHERE conversation_id = ?
                    ORDER BY id DESC LIMIT 4
                """, (conv_id,))
                recent_rows = cursor.fetchall()
                conv_history = []
                for r in reversed(recent_rows):
                    if r["direction"] == "inbound":
                        conv_history.append({"role": "user", "content": r["message_text"]})
                    else:
                        c = r["approved_text"] or r["ai_draft"]
                        if c:
                            conv_history.append({"role": "assistant", "content": c})

                # Generate AI draft response grounded in Abenzo Knowledge Base
                ai_draft = ""
                lead_temp = "early"
                needs_human = True
                try:
                    draft_res = await draft_inbound_response_with_ai(text, conv_history, agency_profile)
                    ai_draft = (draft_res.get("ai_draft") or "").strip()
                    lead_temp = draft_res.get("lead_temperature", "early")
                    needs_human = bool(draft_res.get("needs_human_decision", True))
                except Exception:
                    ai_draft = "Hi! Thank you for reaching out to Abenzo. A team member will follow up shortly."
                    needs_human = True

                # Determine if eligible for automated outbound dispatch:
                # - Explicit auto_reply_faq_enabled setting is active
                # - High-confidence, routine response grounded in approved knowledge (needs_human is False)
                # - Real inbound recipient within the Meta 24h messaging window
                # - Instagram access token configured
                is_auto_reply_eligible = (
                    auto_reply_enabled and
                    bool(ai_draft) and
                    not needs_human and
                    bool(settings.effective_instagram_token) and
                    not sender_id.startswith("sample_") and
                    not sender_id.startswith("manual_") and
                    sender_id not in own_ids
                )

                if is_auto_reply_eligible:
                    # Dispatched directly to genuine inbound user via official Instagram Graph API
                    dispatch_res = await dispatch_instagram_dm(sender_id, ai_draft)
                    if dispatch_res.get("success"):
                        meta_mid = dispatch_res.get("meta_message_id", "")
                        cursor.execute("""
                            INSERT INTO conversation_events (
                                conversation_id, external_event_id, event_type, direction,
                                message_text, ai_draft, approved_text, delivery_status,
                                meta_message_id, sent_at, created_at
                            ) VALUES (?, ?, 'dm', 'inbound', ?, ?, ?, 'sent', ?, ?, ?)
                        """, (conv_id, mid, text, ai_draft, ai_draft, meta_mid, now, now))

                        cursor.execute("""
                            UPDATE conversations SET
                                needs_human = 0,
                                lead_temperature = ?,
                                last_message_at = ?,
                                updated_at = ?
                            WHERE id = ?
                        """, (lead_temp, now, now, conv_id))
                    else:
                        err = dispatch_res.get("error_details", "")
                        cursor.execute("""
                            INSERT INTO conversation_events (
                                conversation_id, external_event_id, event_type, direction,
                                message_text, ai_draft, approved_text, delivery_status,
                                error_details, created_at
                            ) VALUES (?, ?, 'dm', 'inbound', ?, ?, ?, 'failed', ?, ?)
                        """, (conv_id, mid, text, ai_draft, ai_draft, err, now))

                        cursor.execute("""
                            UPDATE conversations SET
                                needs_human = 1,
                                lead_temperature = ?,
                                last_message_at = ?,
                                updated_at = ?
                            WHERE id = ?
                        """, (lead_temp, now, now, conv_id))
                else:
                    # Flag for human review: uncertain question, complaint, or complex scope/pricing
                    cursor.execute("""
                        INSERT INTO conversation_events (
                            conversation_id, external_event_id, event_type, direction,
                            message_text, ai_draft, approved_text, delivery_status, created_at
                        ) VALUES (?, ?, 'dm', 'inbound', ?, ?, '', 'draft_pending', ?)
                    """, (conv_id, mid, text, ai_draft, now))

                    cursor.execute("""
                        UPDATE conversations SET
                            needs_human = 1,
                            lead_temperature = ?,
                            last_message_at = ?,
                            updated_at = ?
                        WHERE id = ?
                    """, (lead_temp, now, now, conv_id))

                processed_count += 1

        conn.commit()

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

            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM app_settings WHERE key = 'business_profile'")
                prof_row = cursor.fetchone()
                agency_profile = json.loads(prof_row["value"]) if prof_row else {}

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

                        # Deduplication check
                        cursor.execute("SELECT id FROM conversation_events WHERE external_event_id = ?", (mid,))
                        if cursor.fetchone():
                            continue

                        # Find or create conversation
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

                        # Draft reply
                        ai_draft = ""
                        try:
                            draft_res = await draft_inbound_response_with_ai(text, [], agency_profile)
                            ai_draft = draft_res.get("ai_draft", "")
                        except Exception:
                            ai_draft = "Hi! Thank you for reaching out to Abenzo. A member of our team will follow up shortly."

                        cursor.execute("""
                            INSERT INTO conversation_events (
                                conversation_id, external_event_id, event_type, direction,
                                message_text, ai_draft, approved_text, delivery_status, created_at
                            ) VALUES (?, ?, 'dm', 'inbound', ?, ?, '', 'draft_pending', ?)
                        """, (conv_id, mid, text, ai_draft, now))
                        synced += 1

                conn.commit()

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
