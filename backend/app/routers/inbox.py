import json
import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from backend.app.database import get_db
from backend.app.schemas import (
    ConversationResponse,
    ConversationEventResponse,
    ConversationEventCreate,
    SendReplyRequest,
    SendReplyResponse
)
from backend.app.services.ollama_service import draft_inbound_response_with_ai

router = APIRouter(prefix="/inbox", tags=["inbox"])

@router.get("/conversations", response_model=List[ConversationResponse])
def get_conversations(needs_human: Optional[int] = None, status: Optional[str] = None):
    with get_db() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM conversations WHERE 1=1"
        params = []
        if needs_human is not None:
            query += " AND needs_human = ?"
            params.append(needs_human)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY last_message_at DESC, id DESC"
        cursor.execute(query, params)
        conv_rows = cursor.fetchall()

        conversations = []
        for c in conv_rows:
            c_dict = dict(c)
            cursor.execute("""
                SELECT * FROM conversation_events
                WHERE conversation_id = ?
                ORDER BY created_at ASC, id ASC
            """, (c_dict["id"],))
            events = [dict(e) for e in cursor.fetchall()]
            c_dict["events"] = events
            conversations.append(c_dict)

        return conversations

@router.get("/conversations/{conv_id}", response_model=ConversationResponse)
def get_conversation(conv_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,))
        conv = cursor.fetchone()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        c_dict = dict(conv)
        cursor.execute("""
            SELECT * FROM conversation_events
            WHERE conversation_id = ?
            ORDER BY created_at ASC, id ASC
        """, (conv_id,))
        c_dict["events"] = [dict(e) for e in cursor.fetchall()]
        return c_dict

@router.post("/events/create", response_model=ConversationEventResponse)
async def create_inbound_event(event_in: ConversationEventCreate):
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Verify conversation exists
        cursor.execute("SELECT id FROM conversations WHERE id = ?", (event_in.conversation_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Check idempotency if external_event_id provided
        if event_in.external_event_id:
            cursor.execute("SELECT id FROM conversation_events WHERE external_event_id = ?", (event_in.external_event_id,))
            existing = cursor.fetchone()
            if existing:
                raise HTTPException(status_code=409, detail="Duplicate event: external_event_id already processed")

        # Fetch Abenzo profile and prior messages for context
        cursor.execute("SELECT value FROM app_settings WHERE key = 'business_profile'")
        prof_row = cursor.fetchone()
        agency_profile = json.loads(prof_row["value"]) if prof_row else {}

        cursor.execute("""
            SELECT direction, message_text, approved_text FROM conversation_events
            WHERE conversation_id = ? ORDER BY id DESC LIMIT 4
        """, (event_in.conversation_id,))
        prior_events = [dict(r) for r in cursor.fetchall()]

    # Generate AI draft response
    ai_draft_text = ""
    lead_temp = "early"
    try:
        draft_res = await draft_inbound_response_with_ai(
            incoming_message=event_in.message_text,
            conversation_history=prior_events,
            agency_profile=agency_profile
        )
        ai_draft_text = draft_res.get("ai_draft", "")
        lead_temp = draft_res.get("lead_temperature", "early")
    except Exception as e:
        ai_draft_text = "Thank you for reaching out to Abenzo! A member of our team will review your query and respond shortly."

    now = datetime.now().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO conversation_events (
                conversation_id, external_event_id, event_type, direction,
                message_text, ai_draft, approved_text, delivery_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, '', 'draft_pending', ?)
        """, (
            event_in.conversation_id,
            event_in.external_event_id or f"evt_{uuid.uuid4().hex[:12]}",
            event_in.event_type,
            event_in.direction,
            event_in.message_text,
            ai_draft_text,
            now
        ))
        event_id = cursor.lastrowid

        cursor.execute("""
            UPDATE conversations SET
                last_message_at = ?,
                needs_human = 1,
                lead_temperature = ?,
                updated_at = ?
            WHERE id = ?
        """, (now, lead_temp, now, event_in.conversation_id))
        conn.commit()

        cursor.execute("SELECT * FROM conversation_events WHERE id = ?", (event_id,))
        return dict(cursor.fetchone())

@router.post("/events/{event_id}/approve", response_model=ConversationEventResponse)
def approve_event_draft(event_id: int, approved_text: str):
    """
    User human-approval step for inbound replies.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM conversation_events WHERE id = ?", (event_id,))
        event = cursor.fetchone()
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")

        cursor.execute("""
            UPDATE conversation_events SET
                approved_text = ?,
                delivery_status = 'approved'
            WHERE id = ?
        """, (approved_text, event_id))

        cursor.execute("""
            UPDATE conversations SET
                needs_human = 0,
                updated_at = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), event["conversation_id"]))
        conn.commit()

        cursor.execute("SELECT * FROM conversation_events WHERE id = ?", (event_id,))
        return dict(cursor.fetchone())

@router.post("/events/{event_id}/send", response_model=SendReplyResponse)
async def send_event_reply(event_id: int, approved_text: Optional[str] = None):
    """
    Direct inbox action to dispatch an approved reply to Instagram.
    Requires explicit human approval and guards against duplicate sends.
    """
    from backend.app.routers.meta import send_approved_reply
    return await send_approved_reply(SendReplyRequest(event_id=event_id, approved_text=approved_text))

@router.post("/sample-conversation")
async def create_sample_conversation():
    """
    Creates a realistic sample inbound DM conversation clearly labeled as SAMPLE
    for testing the inbox, AI drafting, and approval workflows without official Meta credentials.
    """
    now = datetime.now().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Create sample conversation
        cursor.execute("""
            INSERT INTO conversations (
                platform, external_thread_id, contact_display_name,
                status, needs_human, lead_temperature, notes, created_at, updated_at
            ) VALUES ('instagram_sample', ?, ?, 'active', 1, 'qualified', 'Sample prospect seeking e-commerce redesign', ?, ?)
        """, (f"sample_th_{uuid.uuid4().hex[:8]}", "Sample Client (@kerala_spices_co)", now, now))
        conv_id = cursor.lastrowid

        # Insert sample event
        sample_msg = "Hi Abenzo team! We run an organic spices brand in Kochi and our current website doesn't support online orders. Do you build WhatsApp ordering or Shopify sites?"
        
        cursor.execute("SELECT value FROM app_settings WHERE key = 'business_profile'")
        prof_row = cursor.fetchone()
        agency_profile = json.loads(prof_row["value"]) if prof_row else {}

    ai_draft_text = ""
    try:
        draft_res = await draft_inbound_response_with_ai(
            incoming_message=sample_msg,
            conversation_history=[],
            agency_profile=agency_profile
        )
        ai_draft_text = draft_res.get("ai_draft", "")
    except Exception:
        ai_draft_text = "Hi! Yes, Abenzo builds custom e-commerce and WhatsApp ordering storefronts tailored for Indian businesses. You can check our portfolio at https://abenzo.in/portfolio. Would you like to schedule a 15-minute call to discuss your requirements?"

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO conversation_events (
                conversation_id, external_event_id, event_type, direction,
                message_text, ai_draft, approved_text, delivery_status, created_at
            ) VALUES (?, ?, 'dm', 'inbound', ?, ?, '', 'draft_pending', ?)
        """, (
            conv_id,
            f"sample_evt_{uuid.uuid4().hex[:10]}",
            sample_msg,
            ai_draft_text,
            now
        ))
        conn.commit()

    return {"status": "success", "conversation_id": conv_id, "message": "Sample conversation created successfully (clearly labeled SAMPLE)"}
