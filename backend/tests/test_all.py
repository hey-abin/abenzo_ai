import pytest
import sqlite3
import json
import asyncio
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.database import get_db, init_db
from backend.app.services.discovery_service import normalize_domain_or_url, extract_instagram_handle, check_duplicate_lead
from backend.app.schemas import LeadQualificationOutput
from backend.app.services.website_checker import check_website
from backend.app.services.ollama_service import (
    qualify_lead_with_ai,
    draft_inbound_response_with_ai,
    check_ollama_health
)
import httpx

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test_abenzo.db")
    monkeypatch.setattr("backend.app.config.settings.DB_PATH", test_db)
    init_db(test_db)
    yield test_db

def test_root_api():
    resp = client.get("/api")
    assert resp.status_code == 200
    assert resp.json()["status"] == "online"

def test_normalization_and_deduplication():
    # URL normalization
    assert normalize_domain_or_url("https://www.example.com/shop/?ref=123") == "example.com/shop"
    assert normalize_domain_or_url("http://example.com/") == "example.com"
    
    # Instagram handle extraction
    assert extract_instagram_handle("https://instagram.com/abenzo_agency/") == "abenzo_agency"
    assert extract_instagram_handle("@abenzo_agency") == "abenzo_agency"

    # Test DB deduplication check
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO leads (business_name, website_url, instagram_url, created_at, updated_at)
            VALUES ('Abenzo Digital', 'https://abenzo.in', 'https://instagram.com/abenzo_in', datetime('now'), datetime('now'))
        """)
        conn.commit()

        # Duplicate by website
        dup1 = check_duplicate_lead(cursor, "Different Name", "http://www.abenzo.in/about")
        assert dup1 is not None
        assert dup1["matched_by"] == "website_url"

        # Duplicate by Instagram
        dup2 = check_duplicate_lead(cursor, "Another Name", "", "@abenzo_in")
        assert dup2 is not None
        assert dup2["matched_by"] == "instagram_handle"

        # Duplicate by business name
        dup3 = check_duplicate_lead(cursor, "abenzo digital", "", "")
        assert dup3 is not None
        assert dup3["matched_by"] == "business_name"

        # Non-duplicate
        dup4 = check_duplicate_lead(cursor, "New Unique Brand", "https://uniquebrand.co.in", "@uniquebrand")
        assert dup4 is None

def test_create_and_update_lead():
    payload = {
        "business_name": "Kochi Artisan Bakery",
        "industry": "Food & Beverage",
        "state": "Kerala",
        "website_url": "https://kochiartisanbakery.in",
        "instagram_url": "https://instagram.com/kochiartisanbakery"
    }
    resp = client.post("/api/leads", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["business_name"] == "Kochi Artisan Bakery"
    assert data["outreach_status"] == "new"
    lead_id = data["id"]

    # Prevent duplicate
    dup_resp = client.post("/api/leads", json=payload)
    assert dup_resp.status_code == 409

    # Update status to approved
    patch_resp = client.patch(f"/api/leads/{lead_id}", json={"outreach_status": "approved"})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["outreach_status"] == "approved"

    # Update to opt-out
    opt_resp = client.patch(f"/api/leads/{lead_id}", json={"outreach_status": "do_not_contact"})
    assert opt_resp.status_code == 200
    assert opt_resp.json()["outreach_status"] == "do_not_contact"

def test_webhook_idempotency():
    # Verify challenge verification
    ver_resp = client.get("/api/meta/webhook?hub.mode=subscribe&hub.challenge=test_challenge_123&hub.verify_token=abenzo_verify_token_sample")
    assert ver_resp.status_code == 200
    assert ver_resp.text == "test_challenge_123"

    # Webhook inbound message event
    webhook_payload = {
        "entry": [
            {
                "messaging": [
                    {
                        "sender": {"id": "ig_user_889"},
                        "message": {
                            "mid": "mid_unique_event_9988",
                            "text": "Hello, how much does a web development project cost?"
                        }
                    }
                ]
            }
        ]
    }
    
    # First delivery
    resp1 = client.post("/api/meta/webhook", json=webhook_payload)
    assert resp1.status_code == 200
    assert resp1.json()["events_processed"] == 1

    # Second delivery (duplicate event mid) -> must be idempotent (0 processed)
    resp2 = client.post("/api/meta/webhook", json=webhook_payload)
    assert resp2.status_code == 200
    assert resp2.json()["events_processed"] == 0

def test_inbound_webhook_auto_reply_flow(monkeypatch):
    """
    Verifies the complete inbound-to-outbound reply workflow:
    1. Routine high-confidence inquiry dispatches automatically via Meta Graph API and sets delivery_status='sent'.
    2. Uncertain or complex inquiry sets delivery_status='draft_pending' and needs_human=1.
    3. Outbound echo messages are ignored.
    """
    dispatched_calls = []

    async def mock_dispatch(recipient_id, text):
        dispatched_calls.append({"recipient_id": recipient_id, "text": text})
        return {"success": True, "meta_message_id": f"mid_auto_{len(dispatched_calls)}", "error_details": ""}

    monkeypatch.setattr("backend.app.routers.meta.dispatch_instagram_dm", mock_dispatch)
    monkeypatch.setattr("backend.app.config.settings.META_ACCESS_TOKEN", "test_ig_token_abc")

    # 1. Echo message should be discarded
    echo_payload = {
        "entry": [{
            "messaging": [{
                "sender": {"id": "ig_user_auto_1"},
                "message": {
                    "mid": "mid_echo_001",
                    "text": "Outbound echo message",
                    "is_echo": True
                }
            }]
        }]
    }
    resp_echo = client.post("/api/meta/webhook", json=echo_payload)
    assert resp_echo.status_code == 200
    assert resp_echo.json()["events_processed"] == 0
    assert len(dispatched_calls) == 0

    # 2. Routine high-confidence inquiry (requires explicit auto_reply_faq_enabled)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_settings WHERE key = 'business_profile'")
        r = cursor.fetchone()
        p = json.loads(r["value"]) if r else {}
        p["auto_reply_faq_enabled"] = True
        cursor.execute("UPDATE app_settings SET value = ? WHERE key = 'business_profile'", (json.dumps(p),))
        conn.commit()

    async def mock_draft_routine(*args, **kwargs):
        return {
            "ai_draft": "Abenzo Starter Package starts at ₹15,000+ for 3-5 pages.",
            "reasoning": "Standard FAQ response.",
            "lead_temperature": "qualified",
            "needs_human_decision": False,
            "matched_faq_question": "What are your prices?",
            "source_references": ["https://abenzo.in/pricing"]
        }

    monkeypatch.setattr("backend.app.routers.meta.draft_inbound_response_with_ai", mock_draft_routine)

    routine_payload = {
        "entry": [{
            "messaging": [{
                "sender": {"id": "ig_user_auto_routine_1"},
                "message": {
                    "mid": "mid_auto_routine_001",
                    "text": "What is the price for a starter website?"
                }
            }]
        }]
    }
    resp_routine = client.post("/api/meta/webhook", json=routine_payload)
    assert resp_routine.status_code == 200
    assert resp_routine.json()["events_processed"] == 1
    assert len(dispatched_calls) == 1
    assert dispatched_calls[0]["recipient_id"] == "ig_user_auto_routine_1"

    # Verify event and conversation in DB
    with get_db() as conn:
        cursor = conn.cursor()
        # Inbound event persisted immediately
        cursor.execute("SELECT * FROM conversation_events WHERE external_event_id = 'mid_auto_routine_001'")
        in_ev = dict(cursor.fetchone())
        assert in_ev["direction"] == "inbound"
        assert in_ev["delivery_status"] == "received"

        # Outbound event persisted after dispatch
        cursor.execute("SELECT * FROM conversation_events WHERE conversation_id = ? AND direction = 'outbound'", (in_ev["conversation_id"],))
        out_ev = dict(cursor.fetchone())
        assert out_ev["delivery_status"] == "sent"
        assert out_ev["meta_message_id"] == "mid_auto_1"
        assert out_ev["message_text"] == "Abenzo Starter Package starts at ₹15,000+ for 3-5 pages."

        cursor.execute("SELECT needs_human FROM conversations WHERE external_thread_id = 'ig_user_auto_routine_1'")
        assert cursor.fetchone()["needs_human"] == 0

    # 3. Complex inquiry requiring human decision
    async def mock_draft_complex(*args, **kwargs):
        return {
            "ai_draft": "Hi! We'd love to learn more about your custom enterprise architecture.",
            "reasoning": "Custom quote required.",
            "lead_temperature": "ready_for_human",
            "needs_human_decision": True,
            "matched_faq_question": None,
            "source_references": []
        }

    monkeypatch.setattr("backend.app.routers.meta.draft_inbound_response_with_ai", mock_draft_complex)

    complex_payload = {
        "entry": [{
            "messaging": [{
                "sender": {"id": "ig_user_auto_complex_1"},
                "message": {
                    "mid": "mid_auto_complex_001",
                    "text": "Can you build a high-frequency trading web portal with custom hardware integration for $200?"
                }
            }]
        }]
    }
    resp_complex = client.post("/api/meta/webhook", json=complex_payload)
    assert resp_complex.status_code == 200
    assert resp_complex.json()["events_processed"] == 1
    # Dispatch count must NOT have increased
    assert len(dispatched_calls) == 1

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM conversation_events WHERE external_event_id = 'mid_auto_complex_001'")
        ev = dict(cursor.fetchone())
        assert ev["delivery_status"] == "received"

        # Outbound draft pending event
        cursor.execute("SELECT * FROM conversation_events WHERE conversation_id = ? AND direction = 'outbound'", (ev["conversation_id"],))
        draft_ev = dict(cursor.fetchone())
        assert draft_ev["delivery_status"] == "draft_pending"

        cursor.execute("SELECT needs_human FROM conversations WHERE external_thread_id = 'ig_user_auto_complex_1'")
        assert cursor.fetchone()["needs_human"] == 1

def test_dashboard_send_conversation_reply(monkeypatch):
    """Verifies that the dashboard can send messages directly in an ongoing conversation."""
    # 1. Sample thread simulated reply
    sample_resp = client.post("/api/inbox/sample-conversation")
    conv_id = sample_resp.json()["conversation_id"]

    reply_resp = client.post(f"/api/inbox/conversations/{conv_id}/reply", json={
        "message_text": "Hello, thank you for reaching out!"
    })
    assert reply_resp.status_code == 200
    assert reply_resp.json()["status"] == "sent"
    assert reply_resp.json()["delivery_status"] == "sent"

    # 2. Live Instagram thread reply with dispatch
    dispatched = []
    async def mock_dispatch(recipient_id, text):
        dispatched.append({"recipient_id": recipient_id, "text": text})
        return {"success": True, "meta_message_id": "mid_dash_reply_001", "error_details": ""}

    monkeypatch.setattr("backend.app.routers.meta.dispatch_instagram_dm", mock_dispatch)

    with get_db() as conn:
        cursor = conn.cursor()
        now = "2026-10-18T12:00:00"
        cursor.execute("""
            INSERT INTO conversations (platform, external_thread_id, recipient_id, contact_display_name, status, needs_human, created_at, updated_at)
            VALUES ('instagram', 'ig_user_dash_test', 'ig_user_dash_test', 'IG Dash User', 'active', 1, ?, ?)
        """, (now, now))
        live_conv_id = cursor.lastrowid
        conn.commit()

    live_reply = client.post(f"/api/inbox/conversations/{live_conv_id}/reply", json={
        "message_text": "Live reply from dashboard to Instagram user"
    })
    assert live_reply.status_code == 200
    assert live_reply.json()["status"] == "sent"
    assert len(dispatched) == 1
    assert dispatched[0]["recipient_id"] == "ig_user_dash_test"

def test_human_approval_rule_for_inbox():
    # Create sample conversation
    sample_resp = client.post("/api/inbox/sample-conversation")
    assert sample_resp.status_code == 200
    conv_id = sample_resp.json()["conversation_id"]

    # Verify conversation requires human
    conv = client.get(f"/api/inbox/conversations/{conv_id}").json()
    assert conv["needs_human"] == 1
    assert len(conv["events"]) >= 1
    event = conv["events"][0]
    assert event["delivery_status"] == "draft_pending"

    # Human approves draft
    appr_resp = client.post(
        f"/api/inbox/events/{event['id']}/approve?approved_text=Approved%20response%20by%20Abin"
    )
    assert appr_resp.status_code == 200
    assert appr_resp.json()["delivery_status"] == "approved"

    # Verify needs_human is cleared
    conv_updated = client.get(f"/api/inbox/conversations/{conv_id}").json()
    assert conv_updated["needs_human"] == 0

def test_ai_qualification_schema_validation():
    # Validate Pydantic schema validation for Ollama output
    valid_data = {
        "business_summary": "Handcrafted leather goods brand in Bangalore with active Instagram presence.",
        "industry": "Retail & Fashion",
        "website_status": "not_found",
        "website_evidence_summary": "Domain not configured in Instagram bio; no active website found.",
        "lead_score": 88,
        "confidence": "high",
        "opportunity": "Direct-to-consumer storefront with catalog showcase",
        "recommended_service": "E-commerce & WhatsApp Ordering Storefronts",
        "personalized_dm": "Hi! Came across your leather goods brand and loved the craftsmanship in your recent collection. If you're planning to give your customers an easy way to browse and order online, Abenzo may be able to help. Open to a couple of ideas?",
        "reasoning_summary": "High Instagram activity without e-commerce website represents clear high-fit need.",
        "next_best_action": "Send personalized outreach DM via manual Instagram review."
    }
    model = LeadQualificationOutput(**valid_data)
    assert model.lead_score == 88
    assert model.confidence == "high"

def test_instagram_status_and_missing_credentials(monkeypatch):
    # Test missing credentials
    monkeypatch.setattr("backend.app.config.settings.INSTAGRAM_ACCESS_TOKEN", "")
    monkeypatch.setattr("backend.app.config.settings.META_ACCESS_TOKEN", "")
    
    resp = client.get("/api/meta/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is False
    assert data["status"] == "not_configured"
    assert "access_token" not in data  # Token must never be in response

def test_instagram_webhook_signature_verification(monkeypatch):
    import hmac
    import hashlib

    secret = "test_app_secret_12345"
    monkeypatch.setattr("backend.app.config.settings.INSTAGRAM_APP_SECRET", secret)

    payload = json.dumps({"entry": [{"messaging": [{"sender": {"id": "user1"}, "message": {"mid": "sig_mid_1", "text": "Hi"}}]}]}).encode("utf-8")
    
    # 1. Invalid signature
    bad_resp = client.post("/api/meta/webhook", content=payload, headers={"X-Hub-Signature-256": "sha256=invalidhex"})
    assert bad_resp.status_code == 403

    # 2. Valid signature
    valid_sig = "sha256=" + hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    good_resp = client.post("/api/meta/webhook", content=payload, headers={"X-Hub-Signature-256": valid_sig})
    assert good_resp.status_code == 200
    assert good_resp.json()["events_processed"] == 1

def test_knowledge_items_crud_and_persistence():
    # 1. Create custom fact
    new_fact = {
        "category": "package",
        "title": "Starter Package (₹15,000+)",
        "content": "Starting Price: ₹15,000+\nInclusions: 3–5 pages, responsive design, WhatsApp integration, basic SEO",
        "source_url": "https://abenzo.vercel.app/llms.txt",
        "verification_status": "approved"
    }
    create_resp = client.post("/api/knowledge", json=new_fact)
    assert create_resp.status_code == 200
    fact_id = create_resp.json()["id"]

    # 2. Fetch facts
    get_resp = client.get("/api/knowledge?category=package")
    assert get_resp.status_code == 200
    items = get_resp.json()
    assert any(i["id"] == fact_id for i in items)

    # 3. Update fact
    update_resp = client.patch(f"/api/knowledge/{fact_id}", json={"verification_status": "pending_review"})
    assert update_resp.status_code == 200
    assert update_resp.json()["verification_status"] == "pending_review"

    # 4. Delete fact
    del_resp = client.delete(f"/api/knowledge/{fact_id}")
    assert del_resp.status_code == 200

def test_outbound_delivery_success(monkeypatch):
    """Verifies successful outbound message dispatch and distinct state updates."""
    with get_db() as conn:
        cursor = conn.cursor()
        now = "2026-10-17T12:00:00"
        cursor.execute("""
            INSERT INTO conversations (platform, external_thread_id, recipient_id, contact_display_name, status, needs_human, created_at, updated_at)
            VALUES ('instagram', 'ig_user_7788', 'ig_user_7788', 'IG User 7788', 'active', 1, ?, ?)
        """, (now, now))
        conv_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO conversation_events (conversation_id, external_event_id, event_type, direction, message_text, ai_draft, delivery_status, created_at)
            VALUES (?, 'mid_inbound_7788', 'dm', 'inbound', 'Need a website', 'Abenzo pricing is ₹15k+', 'draft_pending', ?)
        """, (conv_id, now))
        event_id = cursor.lastrowid
        conn.commit()

    # Mock dispatch_instagram_dm to return success
    async def mock_dispatch(recipient_id, text):
        assert recipient_id == "ig_user_7788"
        assert text == "Approved custom response for 7788"
        return {"success": True, "meta_message_id": "meta_mid_test_9999", "error_details": ""}

    monkeypatch.setattr("backend.app.routers.meta.dispatch_instagram_dm", mock_dispatch)

    # Dispatch reply
    resp = client.post("/api/meta/send-reply", json={
        "event_id": event_id,
        "approved_text": "Approved custom response for 7788"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "sent"
    assert data["delivery_status"] == "sent"
    assert data["meta_message_id"] == "meta_mid_test_9999"
    assert data["recipient_id"] == "ig_user_7788"

    # Verify database persistence
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM conversation_events WHERE id = ?", (event_id,))
        ev = dict(cursor.fetchone())
        assert ev["delivery_status"] == "sent"
        assert ev["meta_message_id"] == "meta_mid_test_9999"
        assert ev["approved_text"] == "Approved custom response for 7788"
        assert ev["error_details"] == ""
        assert ev["sent_at"] != ""

        cursor.execute("SELECT needs_human FROM conversations WHERE id = ?", (conv_id,))
        assert cursor.fetchone()["needs_human"] == 0

def test_outbound_delivery_api_failure_and_sanitization(monkeypatch):
    """Verifies that API failures are sanitized, recorded as failed, and never leak credentials."""
    with get_db() as conn:
        cursor = conn.cursor()
        now = "2026-10-17T12:00:00"
        cursor.execute("""
            INSERT INTO conversations (platform, external_thread_id, recipient_id, contact_display_name, status, needs_human, created_at, updated_at)
            VALUES ('instagram', 'ig_user_fail_1', 'ig_user_fail_1', 'IG Fail User', 'active', 1, ?, ?)
        """, (now, now))
        conv_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO conversation_events (conversation_id, external_event_id, event_type, direction, message_text, ai_draft, delivery_status, created_at)
            VALUES (?, 'mid_inbound_fail_1', 'dm', 'inbound', 'Hi', 'Draft reply', 'draft_pending', ?)
        """, (conv_id, now))
        event_id = cursor.lastrowid
        conn.commit()

    # Mock dispatch failure
    async def mock_dispatch_fail(recipient_id, text):
        return {
            "success": False,
            "meta_message_id": "",
            "error_details": "Meta API error [100]: (#100) The recipient ID is invalid or outside 24h messaging window"
        }

    monkeypatch.setattr("backend.app.routers.meta.dispatch_instagram_dm", mock_dispatch_fail)

    # Attempt send
    resp = client.post("/api/meta/send-reply", json={
        "event_id": event_id,
        "approved_text": "Approved reply"
    })
    assert resp.status_code == 502
    assert "The recipient ID is invalid" in resp.json()["detail"]
    assert "token" not in resp.text.lower()
    assert "secret" not in resp.text.lower()

    # Verify event marked as failed with sanitized details
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM conversation_events WHERE id = ?", (event_id,))
        ev = dict(cursor.fetchone())
        assert ev["delivery_status"] == "failed"
        assert "Meta API error [100]" in ev["error_details"]

def test_outbound_duplicate_send_prevention():
    """Verifies that messages already sent or transmitting cannot be resent."""
    with get_db() as conn:
        cursor = conn.cursor()
        now = "2026-10-17T12:00:00"
        cursor.execute("""
            INSERT INTO conversations (platform, external_thread_id, recipient_id, contact_display_name, status, needs_human, created_at, updated_at)
            VALUES ('instagram', 'ig_user_dup_1', 'ig_user_dup_1', 'IG User Dup', 'active', 1, ?, ?)
        """, (now, now))
        conv_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO conversation_events (conversation_id, external_event_id, event_type, direction, message_text, approved_text, meta_message_id, delivery_status, created_at)
            VALUES (?, 'mid_sent_dup', 'dm', 'outbound', 'Already sent', 'Already sent', 'meta_mid_existing', 'sent', ?)
        """, (conv_id, now))
        sent_event_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO conversation_events (conversation_id, external_event_id, event_type, direction, message_text, approved_text, delivery_status, created_at)
            VALUES (?, 'mid_sending_dup', 'dm', 'outbound', 'In flight', 'In flight', 'sending', ?)
        """, (conv_id, now))
        sending_event_id = cursor.lastrowid
        conn.commit()

    # Attempt resend on 'sent' event
    resp1 = client.post("/api/meta/send-reply", json={"event_id": sent_event_id, "approved_text": "Try again"})
    assert resp1.status_code == 409
    assert "Duplicate send prevented" in resp1.json()["detail"]

    # Attempt resend on 'sending' event
    resp2 = client.post("/api/meta/send-reply", json={"event_id": sending_event_id, "approved_text": "Try again"})
    assert resp2.status_code == 409
    assert "currently being transmitted" in resp2.json()["detail"]

def test_outbound_invalid_recipient_and_cold_dm_rejection():
    """Verifies that sample/manual conversations or cold DMs without approved text are rejected."""
    # 1. Create a sample conversation (manual platform)
    sample_resp = client.post("/api/inbox/sample-conversation")
    assert sample_resp.status_code == 200
    conv_id = sample_resp.json()["conversation_id"]

    conv = client.get(f"/api/inbox/conversations/{conv_id}").json()
    sample_event_id = conv["events"][0]["id"]

    # Reject sample conversation delivery
    resp = client.post("/api/meta/send-reply", json={
        "event_id": sample_event_id,
        "approved_text": "Sample test reply"
    })
    assert resp.status_code == 400
    assert "Invalid recipient ID" in resp.json()["detail"] or "platform" in resp.json()["detail"]

    # 2. Reject unapproved blank text
    with get_db() as conn:
        cursor = conn.cursor()
        now = "2026-10-17T12:00:00"
        cursor.execute("""
            INSERT INTO conversations (platform, external_thread_id, recipient_id, contact_display_name, status, needs_human, created_at, updated_at)
            VALUES ('instagram', 'ig_user_no_appr', 'ig_user_no_appr', 'IG User', 'active', 1, ?, ?)
        """, (now, now))
        c_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO conversation_events (conversation_id, external_event_id, event_type, direction, message_text, approved_text, delivery_status, created_at)
            VALUES (?, 'mid_no_appr', 'dm', 'inbound', 'Query', '', 'draft_pending', ?)
        """, (c_id, now))
        e_id = cursor.lastrowid
        conn.commit()

    resp_blank = client.post("/api/meta/send-reply", json={"event_id": e_id, "approved_text": "   "})
    assert resp_blank.status_code == 400
    assert "Human approval required" in resp_blank.json()["detail"]

@pytest.mark.anyio
async def test_openai_compatible_provider_lead_qualification(monkeypatch):
    """Tests OpenAI-compatible hosted provider adapter for lead qualification."""
    monkeypatch.setattr("backend.app.config.settings.AI_PROVIDER", "openai_compatible")
    monkeypatch.setattr("backend.app.config.settings.AI_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setattr("backend.app.config.settings.AI_API_KEY", "gsk_dummy_test_key_123")
    monkeypatch.setattr("backend.app.config.settings.AI_MODEL", "llama-3.1-8b-instant")

    mock_json_content = json.dumps({
        "business_summary": "Handcrafted pottery store in Jaipur with active online portfolio.",
        "industry": "Home & Decor",
        "website_status": "not_found",
        "website_evidence_summary": "Active Instagram bio lacks verified custom website.",
        "lead_score": 82,
        "confidence": "high",
        "opportunity": "Modern e-commerce storefront with catalog showcase",
        "recommended_service": "E-commerce & WhatsApp Ordering Storefronts",
        "personalized_dm": "Hi! Loved the handcrafted ceramic collection on your feed. If you are looking to make catalog ordering smoother for customers, Abenzo can help.",
        "reasoning_summary": "Clear fit for digital storefront given high Instagram engagement.",
        "next_best_action": "Manual review of DM draft before dispatch."
    })

    async def mock_post(*args, **kwargs):
        assert kwargs["headers"]["Authorization"] == "Bearer gsk_dummy_test_key_123"
        assert kwargs["json"]["model"] == "llama-3.1-8b-instant"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": mock_json_content}}]
        }
        return mock_resp

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        lead_data = {
            "business_name": "Jaipur Ceramics",
            "industry": "Home & Decor",
            "state": "Rajasthan",
            "website_status": "not_found"
        }
        result = await qualify_lead_with_ai(lead_data, {})
        assert result.lead_score == 82
        assert result.confidence == "high"
        assert result.recommended_service == "E-commerce & WhatsApp Ordering Storefronts"

@pytest.mark.anyio
async def test_openai_compatible_provider_markdown_fences_stripping(monkeypatch):
    """Verifies that markdown code blocks (```json ... ```) from LLMs are safely parsed."""
    monkeypatch.setattr("backend.app.config.settings.AI_PROVIDER", "openai_compatible")
    monkeypatch.setattr("backend.app.config.settings.AI_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setattr("backend.app.config.settings.AI_API_KEY", "gsk_test_key")
    monkeypatch.setattr("backend.app.config.settings.AI_MODEL", "llama-3.1-8b-instant")

    fenced_content = """```json
{
  "ai_draft": "Hello! Abenzo offers custom web development starting from our Starter Package at ₹15,000+.",
  "reasoning": "Direct response matching verified Starter package pricing.",
  "lead_temperature": "qualified",
  "needs_human_decision": true,
  "matched_faq_question": "What packages do you offer?",
  "source_references": ["https://abenzo.vercel.app/llms.txt"]
}
```"""

    async def mock_post(*args, **kwargs):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": fenced_content}}]
        }
        return mock_resp

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        res = await draft_inbound_response_with_ai("How much does a starter site cost?", [], {})
        assert res["lead_temperature"] == "qualified"
        assert "Starter Package" in res["ai_draft"]
        assert res["needs_human_decision"] is True

@pytest.mark.anyio
async def test_openai_compatible_rate_limit_and_timeout(monkeypatch):
    """Verifies that HTTP 429 rate limits and timeouts raise clean, non-leaking errors."""
    monkeypatch.setattr("backend.app.config.settings.AI_PROVIDER", "openai_compatible")
    monkeypatch.setattr("backend.app.config.settings.AI_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setattr("backend.app.config.settings.AI_API_KEY", "gsk_test_key")
    monkeypatch.setattr("backend.app.config.settings.AI_MODEL", "llama-3.1-8b-instant")

    # 1. Rate limit (HTTP 429)
    async def mock_post_429(*args, **kwargs):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = "Rate limit reached"
        return mock_resp

    with patch("httpx.AsyncClient.post", side_effect=mock_post_429):
        with pytest.raises(RuntimeError) as exc_info:
            await draft_inbound_response_with_ai("Pricing?", [], {})
        assert "rate limit" in str(exc_info.value).lower()
        assert "gsk_test_key" not in str(exc_info.value)  # Ensure API key is never leaked

    # 2. Timeout
    async def mock_post_timeout(*args, **kwargs):
        raise httpx.TimeoutException("Read timed out")

    with patch("httpx.AsyncClient.post", side_effect=mock_post_timeout):
        with pytest.raises(RuntimeError) as exc_info:
            await draft_inbound_response_with_ai("Pricing?", [], {})
        assert "timed out" in str(exc_info.value).lower()

@pytest.mark.anyio
async def test_openai_compatible_missing_credentials(monkeypatch):
    """Verifies clean handling when AI_API_KEY or AI_BASE_URL is missing."""
    monkeypatch.setattr("backend.app.config.settings.AI_PROVIDER", "openai_compatible")
    monkeypatch.setattr("backend.app.config.settings.AI_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setattr("backend.app.config.settings.AI_API_KEY", "")

    # Health check reflects missing credentials cleanly
    health = await check_ollama_health()
    assert health.reachable is False
    assert health.provider == "openai_compatible"
    assert "AI_API_KEY is not configured" in health.error_message

    # Completion call raises clean error
    with pytest.raises(RuntimeError) as exc_info:
        await draft_inbound_response_with_ai("Hi", [], {})
    assert "AI_API_KEY is not configured" in str(exc_info.value)

@pytest.mark.anyio
async def test_openai_compatible_health_check(monkeypatch):
    """Verifies health check against OpenAI-compatible endpoint."""
    monkeypatch.setattr("backend.app.config.settings.AI_PROVIDER", "openai_compatible")
    monkeypatch.setattr("backend.app.config.settings.AI_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setattr("backend.app.config.settings.AI_API_KEY", "gsk_test_key")
    monkeypatch.setattr("backend.app.config.settings.AI_MODEL", "llama-3.1-8b-instant")

    # 1. Successful /models response
    async def mock_get_models(*args, **kwargs):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [{"id": "llama-3.1-8b-instant"}, {"id": "qwen-2.5-32b"}]
        }
        return mock_resp

    with patch("httpx.AsyncClient.get", side_effect=mock_get_models):
        health = await check_ollama_health()
        assert health.reachable is True
        assert health.provider == "openai_compatible"
        assert health.model == "llama-3.1-8b-instant"
        assert health.model_installed is True

    # 2. Authentication failure (HTTP 401)
    async def mock_get_auth_fail(*args, **kwargs):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        return mock_resp

    with patch("httpx.AsyncClient.get", side_effect=mock_get_auth_fail):
        health_fail = await check_ollama_health()
        assert health_fail.reachable is False
        assert "invalid AI_API_KEY" in health_fail.error_message

def test_safe_knowledge_seeding_idempotency(tmp_path):
    """Verifies that knowledge seeding is idempotent and preserves existing records."""
    from backend.app.database import seed_initial_knowledge, get_db_connection

    test_db = str(tmp_path / "seed_test.db")
    conn = get_db_connection(test_db)
    cursor = conn.cursor()

    # Create schema
    cursor.execute("""
        CREATE TABLE knowledge_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            source_url TEXT NOT NULL,
            retrieval_time TEXT NOT NULL,
            verification_status TEXT DEFAULT 'approved',
            raw_metadata TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)
    conn.commit()

    # 1. Initial seeding on fresh database -> 20 items seeded
    count1 = seed_initial_knowledge(cursor)
    conn.commit()
    assert count1 == 20

    cursor.execute("SELECT COUNT(*) FROM knowledge_items")
    assert cursor.fetchone()[0] == 20

    # 2. Re-run seeding on already-seeded database -> 0 items added (idempotent)
    count2 = seed_initial_knowledge(cursor)
    conn.commit()
    assert count2 == 0

    cursor.execute("SELECT COUNT(*) FROM knowledge_items")
    assert cursor.fetchone()[0] == 20

    # 3. Simulate user modifying an existing fact -> seeding must NOT overwrite user edit
    cursor.execute("""
        UPDATE knowledge_items
        SET content = 'Custom operator-edited package details'
        WHERE title = 'Starter Package (₹15,000+)'
    """)
    conn.commit()

    count3 = seed_initial_knowledge(cursor)
    conn.commit()
    assert count3 == 0

    cursor.execute("SELECT content FROM knowledge_items WHERE title = 'Starter Package (₹15,000+)'")
    assert cursor.fetchone()[0] == "Custom operator-edited package details"

    conn.close()


def test_get_db_dead_connection_does_not_mask_original_exception(monkeypatch):
    """
    Verifies that if a connection is terminated and rollback fails with an OperationalError,
    get_db() does NOT mask the original exception with psycopg.OperationalError.
    """
    class DeadConnection:
        def __init__(self):
            self.closed = True

        def commit(self):
            pass

        def rollback(self):
            # Simulate psycopg throwing when rollback is attempted on a terminated connection
            raise RuntimeError("psycopg.OperationalError: connection is closed (dead connection)")

        def close(self):
            pass

    monkeypatch.setattr("backend.app.database.get_db_connection", lambda db_path=None: DeadConnection())

    class OriginalQueryTimeoutError(Exception):
        pass

    with pytest.raises(OriginalQueryTimeoutError):
        with get_db() as conn:
            # Simulate IdleInTransactionSessionTimeout raised during query execution
            raise OriginalQueryTimeoutError("terminating connection due to idle-in-transaction timeout")


def test_pg_connection_wrapper_closed_safety():
    """
    Verifies that PgConnectionWrapper handles a closed/terminated psycopg connection safely
    without throwing exceptions during rollback or close.
    """
    from backend.app.database import PgConnectionWrapper

    class MockPsycopgConn:
        def __init__(self):
            self.closed = True

        def rollback(self):
            raise RuntimeError("OperationalError: connection terminated")

        def close(self):
            raise RuntimeError("OperationalError: connection terminated")

    wrapper = PgConnectionWrapper(MockPsycopgConn())
    # Neither rollback nor close should throw
    wrapper.rollback()
    wrapper.close()


def test_webhook_external_calls_happen_outside_db_transactions(monkeypatch):
    """
    Verifies that draft_inbound_response_with_ai and dispatch_instagram_dm are called
    strictly OUTSIDE any database connection context in the webhook handler.
    """
    db_is_open = False
    original_get_db = get_db

    from contextlib import contextmanager
    @contextmanager
    def tracked_get_db(db_path=None):
        nonlocal db_is_open
        with original_get_db(db_path) as conn:
            db_is_open = True
            try:
                yield conn
            finally:
                db_is_open = False

    monkeypatch.setattr("backend.app.routers.meta.get_db", tracked_get_db)
    monkeypatch.setattr("backend.app.config.settings.META_ACCESS_TOKEN", "test_ig_token_abc")

    # Enable auto_reply
    with original_get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_settings WHERE key = 'business_profile'")
        r = cursor.fetchone()
        p = json.loads(r["value"]) if r else {}
        p["auto_reply_faq_enabled"] = True
        cursor.execute("UPDATE app_settings SET value = ? WHERE key = 'business_profile'", (json.dumps(p),))
        conn.commit()

    draft_called_while_db_open = None
    async def mock_draft(*args, **kwargs):
        nonlocal draft_called_while_db_open
        draft_called_while_db_open = db_is_open
        return {
            "ai_draft": "We offer custom websites starting at ₹15,000.",
            "reasoning": "Standard inquiry",
            "lead_temperature": "qualified",
            "needs_human_decision": False
        }

    dispatch_called_while_db_open = None
    async def mock_dispatch(recipient_id, text):
        nonlocal dispatch_called_while_db_open
        dispatch_called_while_db_open = db_is_open
        return {"success": True, "meta_message_id": "mid_tx_test_123"}

    monkeypatch.setattr("backend.app.routers.meta.draft_inbound_response_with_ai", mock_draft)
    monkeypatch.setattr("backend.app.routers.meta.dispatch_instagram_dm", mock_dispatch)

    payload = {
        "entry": [{
            "messaging": [{
                "sender": {"id": "ig_user_boundary_test"},
                "message": {
                    "mid": "mid_boundary_event_001",
                    "text": "What are your services?"
                }
            }]
        }]
    }

    resp = client.post("/api/meta/webhook", json=payload)
    assert resp.status_code == 200
    assert resp.json()["events_processed"] == 1

    # CRUCIAL ASSERTIONS: Neither AI draft nor Instagram dispatch may be called while DB is open!
    assert draft_called_while_db_open is False, "draft_inbound_response_with_ai was called inside get_db()!"
    assert dispatch_called_while_db_open is False, "dispatch_instagram_dm was called inside get_db()!"


def test_two_customers_have_separate_isolated_histories(monkeypatch):
    """
    Verifies that every customer's Instagram conversation is strictly isolated
    by the sender ID, and histories/contexts never leak between customers.
    """
    monkeypatch.setattr("backend.app.config.settings.META_ACCESS_TOKEN", "test_ig_token")

    async def mock_draft(incoming_message, conversation_history, agency_profile, conversation_summary="", lead_context=None):
        return {
            "ai_draft": f"Consultant reply to: {incoming_message}",
            "reasoning": "Separate context",
            "lead_temperature": "qualified",
            "needs_human_decision": False,
            "conversation_summary": f"Summary for {incoming_message}",
            "lead_context": {"requested_service": "Web Design", "business_type": incoming_message}
        }

    monkeypatch.setattr("backend.app.routers.meta.draft_inbound_response_with_ai", mock_draft)

    # Customer 1 message
    payload_1 = {
        "entry": [{
            "messaging": [{
                "sender": {"id": "customer_alpha_101"},
                "message": {"mid": "mid_cust_alpha_01", "text": "I sell handmade ceramics in Goa"}
            }]
        }]
    }
    client.post("/api/meta/webhook", json=payload_1)

    # Customer 2 message
    payload_2 = {
        "entry": [{
            "messaging": [{
                "sender": {"id": "customer_beta_202"},
                "message": {"mid": "mid_cust_beta_01", "text": "We operate a dental clinic in Kochi"}
            }]
        }]
    }
    client.post("/api/meta/webhook", json=payload_2)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM conversations WHERE external_thread_id = 'customer_alpha_101'")
        conv_alpha = dict(cursor.fetchone())
        cursor.execute("SELECT * FROM conversations WHERE external_thread_id = 'customer_beta_202'")
        conv_beta = dict(cursor.fetchone())

        assert conv_alpha["id"] != conv_beta["id"]
        assert "ceramics" in conv_alpha["conversation_summary"]
        assert "dental" in conv_beta["conversation_summary"]

        cursor.execute("SELECT * FROM conversation_events WHERE conversation_id = ?", (conv_alpha["id"],))
        events_alpha = [dict(r) for r in cursor.fetchall()]
        assert all("dental" not in (e["message_text"] or "") for e in events_alpha)

        cursor.execute("SELECT * FROM conversation_events WHERE conversation_id = ?", (conv_beta["id"],))
        events_beta = [dict(r) for r in cursor.fetchall()]
        assert all("ceramics" not in (e["message_text"] or "") for e in events_beta)


def test_history_and_lead_context_loaded_into_prompt(monkeypatch):
    """
    Verifies that recent conversation turns, rolling summary, and structured lead context
    are passed to the AI prompt without data loss.
    """
    captured_prompt = None

    async def mock_call_ai(prompt, **kwargs):
        nonlocal captured_prompt
        captured_prompt = prompt
        return json.dumps({
            "ai_draft": "Got it — an online store for ceramics. Will you need delivery across India?",
            "reasoning": "Probing requirement",
            "lead_temperature": "qualified",
            "needs_human_decision": False,
            "conversation_summary": "Handmade ceramics shop in Goa looking for website.",
            "lead_context": {
                "business_type": "Ceramics Shop",
                "requested_service": "E-commerce Website",
                "requirements": "Online ordering",
                "budget": "Not volunteered",
                "timeline": "Flexible",
                "next_step": "Confirm shipping needs"
            },
            "suggested_conversion_stage": "qualified_lead"
        })

    monkeypatch.setattr("backend.app.services.ollama_service.call_ai_completion", mock_call_ai)

    history = [
        {"role": "user", "text": "I want to build a website for my ceramics store."},
        {"role": "assistant", "text": "Nice! What kind of products will your shop sell?"}
    ]
    lead_ctx = {"business_type": "Ceramics", "requested_service": "Website"}

    result = asyncio.run(draft_inbound_response_with_ai(
        incoming_message="Handmade cups and plates.",
        conversation_history=history,
        agency_profile={"agency_name": "Abenzo"},
        conversation_summary="Customer wants a ceramics store website.",
        lead_context=lead_ctx
    ))

    assert "ceramics" in captured_prompt.lower()
    assert "Handmade cups and plates" in captured_prompt
    assert "Customer wants a ceramics store website" in captured_prompt
    assert result["lead_temperature"] == "qualified"
    assert result["lead_context"]["business_type"] == "Ceramics Shop"


def test_sales_consultant_anti_repetition_and_short_replies(monkeypatch):
    """
    Verifies that messages like 'okay' or 'thanks' do not trigger an unprompted pricing dump,
    and replies adhere to the concise consultant strategy under 45 words.
    """
    captured_prompt = None

    async def mock_call_ai(prompt, **kwargs):
        nonlocal captured_prompt
        captured_prompt = prompt
        return json.dumps({
            "ai_draft": "No rush 😊 What features are most important for your shop?",
            "reasoning": "Acknowledged calmly without pitching",
            "lead_temperature": "engaged",
            "needs_human_decision": False,
            "conversation_summary": "Customer acknowledged, exploring features.",
            "lead_context": {"next_step": "Explore key features"}
        })

    monkeypatch.setattr("backend.app.services.ollama_service.call_ai_completion", mock_call_ai)

    result = asyncio.run(draft_inbound_response_with_ai(
        incoming_message="Ooh okay.",
        conversation_history=[
            {"role": "user", "text": "I want an online clothing store."},
            {"role": "assistant", "text": "Got it! Will you need online payments and delivery options from day one?"}
        ],
        agency_profile={"agency_name": "Abenzo"},
        conversation_summary="Clothing store inquiry.",
        lead_context={"business_type": "Clothing store"}
    ))

    # Prompt must contain the explicit rule preventing pricing dumps on simple acknowledgments
    assert "AVOID UNPROVOKED PRICING DUMPS" in captured_prompt
    assert "Do NOT dump the pricing list" in captured_prompt
    # Reply must be short and conversational
    reply_words = result["ai_draft"].split()
    assert len(reply_words) < 45
    assert "₹" not in result["ai_draft"]


def test_duplicate_webhook_events_idempotency(monkeypatch):
    """
    Verifies that identical inbound webhook message IDs are processed once,
    preventing duplicate database rows and duplicate replies.
    """
    monkeypatch.setattr("backend.app.config.settings.META_ACCESS_TOKEN", "test_ig_token")

    payload = {
        "entry": [{
            "messaging": [{
                "sender": {"id": "user_idempotency_test"},
                "message": {
                    "mid": "mid_unique_idempotency_001",
                    "text": "Hello, do you build Next.js apps?"
                }
            }]
        }]
    }

    # First delivery
    resp1 = client.post("/api/meta/webhook", json=payload)
    assert resp1.status_code == 200
    assert resp1.json()["events_processed"] == 1

    # Second delivery with the same message id
    resp2 = client.post("/api/meta/webhook", json=payload)
    assert resp2.status_code == 200
    assert resp2.json()["events_processed"] == 0

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM conversation_events WHERE external_event_id = 'mid_unique_idempotency_001'")
        assert cursor.fetchone()["count"] == 1


def test_failed_outbound_delivery_handling(monkeypatch):
    """
    Verifies that when the Meta Graph API fails to deliver an outbound message,
    the failure is logged and the event record delivery_status is set to 'failed'.
    """
    monkeypatch.setattr("backend.app.config.settings.META_ACCESS_TOKEN", "test_ig_token")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_settings WHERE key = 'business_profile'")
        r = cursor.fetchone()
        p = json.loads(r["value"]) if r else {}
        p["auto_reply_faq_enabled"] = True
        cursor.execute("UPDATE app_settings SET value = ? WHERE key = 'business_profile'", (json.dumps(p),))
        conn.commit()

    async def mock_draft(*args, **kwargs):
        return {
            "ai_draft": "Our starter package is ₹15,000+.",
            "reasoning": "Standard response",
            "lead_temperature": "qualified",
            "needs_human_decision": False
        }

    async def mock_failed_dispatch(recipient_id, text):
        return {
            "success": False,
            "error_details": "Graph API Error 100: User cannot be messaged (24h window closed)"
        }

    monkeypatch.setattr("backend.app.routers.meta.draft_inbound_response_with_ai", mock_draft)
    monkeypatch.setattr("backend.app.routers.meta.dispatch_instagram_dm", mock_failed_dispatch)

    payload = {
        "entry": [{
            "messaging": [{
                "sender": {"id": "user_failed_delivery_test"},
                "message": {
                    "mid": "mid_delivery_fail_001",
                    "text": "Can I get a quote?"
                }
            }]
        }]
    }

    resp = client.post("/api/meta/webhook", json=payload)
    assert resp.status_code == 200

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM conversation_events WHERE external_event_id = 'mid_delivery_fail_001'")
        in_ev = dict(cursor.fetchone())
        assert in_ev["delivery_status"] == "received"

        cursor.execute("SELECT * FROM conversation_events WHERE conversation_id = ? AND direction = 'outbound'", (in_ev["conversation_id"],))
        out_ev = dict(cursor.fetchone())
        assert out_ev["delivery_status"] == "failed"
        assert "Graph API Error" in out_ev["error_details"]


def test_ai_provider_failure_and_db_resilience(monkeypatch):
    """
    Verifies that when the AI provider times out or raises an error:
    1. The inbound event is NOT lost.
    2. A safe fallback response is drafted.
    3. The conversation is marked as needs_human=1 for manual review.
    """
    monkeypatch.setattr("backend.app.config.settings.META_ACCESS_TOKEN", "test_ig_token")

    async def mock_failing_draft(*args, **kwargs):
        raise RuntimeError("Hosted AI connection timeout")

    monkeypatch.setattr("backend.app.routers.meta.draft_inbound_response_with_ai", mock_failing_draft)

    payload = {
        "entry": [{
            "messaging": [{
                "sender": {"id": "user_ai_failure_test"},
                "message": {
                    "mid": "mid_ai_fail_001",
                    "text": "What are your website packages?"
                }
            }]
        }]
    }

    resp = client.post("/api/meta/webhook", json=payload)
    assert resp.status_code == 200
    assert resp.json()["events_processed"] == 1

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM conversation_events WHERE external_event_id = 'mid_ai_fail_001'")
        in_ev = dict(cursor.fetchone())
        assert in_ev["delivery_status"] == "received"

        cursor.execute("SELECT * FROM conversation_events WHERE conversation_id = ? AND direction = 'outbound'", (in_ev["conversation_id"],))
        out_ev = dict(cursor.fetchone())
        assert out_ev["delivery_status"] == "draft_pending"
        assert "follow up shortly" in out_ev["ai_draft"]

        cursor.execute("SELECT needs_human FROM conversations WHERE id = ?", (in_ev["conversation_id"],))
        assert cursor.fetchone()["needs_human"] == 1


def test_lead_discovery_and_duplicate_detection(monkeypatch):
    """
    Verifies the live lead discovery endpoint:
    - Finds prospects with score reasons and website reachability.
    - Accurately flags existing CRM domains as duplicates.
    - Successfully imports non-duplicate prospects into CRM.
    """
    # 1. Insert an existing lead to test deduplication
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO leads (business_name, website_url, created_at, updated_at)
            VALUES ('Existing Dental Clinic', 'https://existingdental.com', datetime('now'), datetime('now'))
        """)
        conn.commit()

    # 2. Mock external search provider
    from backend.app.services.discovery_service import PublicDirectorySearchProvider

    async def mock_search(self, query, state="", industry="", limit=10):
        return [
            {
                "business_name": "Existing Dental Clinic",
                "website_url": "https://existingdental.com",
                "instagram_url": "",
                "contact_details": "+91 98460 00000",
                "source_url": "https://directory.in/dental",
                "industry": "Healthcare",
                "state": "Kerala",
                "snippet": "Best dental care clinic in Kochi."
            },
            {
                "business_name": "Sunrise Architectural Studio",
                "website_url": "https://sunrisearchitects.in",
                "instagram_url": "",
                "contact_details": "+91 98470 11111",
                "source_url": "https://directory.in/architects",
                "industry": "Architecture",
                "state": "Kerala",
                "snippet": "Contemporary interior and architectural designs."
            }
        ]

    monkeypatch.setattr(PublicDirectorySearchProvider, "search", mock_search)

    # 3. Call discovery endpoint
    disc_resp = client.post("/api/leads/discover", json={
        "niche": "Architecture",
        "location": "Kerala",
        "keywords": "design",
        "limit": 5
    })
    assert disc_resp.status_code == 200
    data = disc_resp.json()
    assert data["status"] == "success"
    assert len(data["results"]) == 2

    # Check deduplication
    res_dental = next(r for r in data["results"] if r["domain"] == "existingdental.com")
    assert res_dental["is_duplicate"] is True

    res_arch = next(r for r in data["results"] if r["domain"] == "sunrisearchitects.in")
    assert res_arch["is_duplicate"] is False
    assert res_arch["lead_score"] > 0
    assert len(res_arch["score_reasons"]) > 0

    # 4. Import the new lead
    import_resp = client.post("/api/leads/import-discovered", json={
        "items": [res_arch]
    })
    assert import_resp.status_code == 200
    import_data = import_resp.json()
    assert import_data["imported_count"] == 1
    assert import_data["skipped_count"] == 0

    # Verify present in leads CRM
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM leads WHERE website_url = 'https://sunrisearchitects.in'")
        imported_lead = cursor.fetchone()
        assert imported_lead is not None
        assert imported_lead["business_name"] == "Sunrise Architectural Studio"


def test_human_takeover_prevents_automatic_replies(monkeypatch):
    """
    Verifies that when a conversation has auto_reply_paused=1 (Human Takeover Active):
    1. Inbound messages are recorded.
    2. Automatic outbound dispatch is blocked, even if auto_reply_faq_enabled=True.
    3. The message is queued as draft_pending.
    4. The human takeover flag can be toggled via PATCH /api/inbox/conversations/{id}.
    """
    monkeypatch.setattr("backend.app.config.settings.META_ACCESS_TOKEN", "test_ig_token")

    # 1. Enable global auto reply
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_settings WHERE key = 'business_profile'")
        r = cursor.fetchone()
        p = json.loads(r["value"]) if r else {}
        p["auto_reply_faq_enabled"] = True
        cursor.execute("UPDATE app_settings SET value = ? WHERE key = 'business_profile'", (json.dumps(p),))
        conn.commit()

    # 2. Create conversation with auto_reply_paused=1
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO conversations (platform, external_thread_id, contact_display_name, auto_reply_paused, created_at, updated_at)
            VALUES ('instagram', 'ig_user_human_takeover_test', 'VIP Client', 1, datetime('now'), datetime('now'))
        """)
        conn.commit()
        cursor.execute("SELECT id FROM conversations WHERE external_thread_id = 'ig_user_human_takeover_test'")
        conv_id = cursor.fetchone()["id"]

    dispatched = []
    async def mock_dispatch(recipient_id, text):
        dispatched.append(text)
        return {"success": True, "meta_message_id": "mid_blocked_test"}

    async def mock_draft(*args, **kwargs):
        return {
            "ai_draft": "Automated response that should be held as draft",
            "reasoning": "Standard answer",
            "lead_temperature": "qualified",
            "needs_human_decision": False
        }

    monkeypatch.setattr("backend.app.routers.meta.dispatch_instagram_dm", mock_dispatch)
    monkeypatch.setattr("backend.app.routers.meta.draft_inbound_response_with_ai", mock_draft)

    # Inbound message arrives
    payload = {
        "entry": [{
            "messaging": [{
                "sender": {"id": "ig_user_human_takeover_test"},
                "message": {
                    "mid": "mid_takeover_001",
                    "text": "What is the cost of website maintenance?"
                }
            }]
        }]
    }
    resp = client.post("/api/meta/webhook", json=payload)
    assert resp.status_code == 200

    # Automated dispatch MUST NOT be called because human takeover is active
    assert len(dispatched) == 0

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM conversation_events WHERE conversation_id = ? AND direction = 'outbound'", (conv_id,))
        out_ev = dict(cursor.fetchone())
        assert out_ev["delivery_status"] == "draft_pending"

    # Test toggling takeover back to automatic via PATCH
    patch_resp = client.patch(f"/api/inbox/conversations/{conv_id}", json={
        "auto_reply_paused": 0,
        "conversion_stage": "consultation_requested"
    })
    assert patch_resp.status_code == 200
    assert patch_resp.json()["auto_reply_paused"] == 0
    assert patch_resp.json()["conversion_stage"] == "consultation_requested"


# ===========================================================================
# Acceptance Tests for Instagram-First Customer Acquisition
# ===========================================================================

def test_instagram_first_discovery_returns_profiles_not_articles(monkeypatch):
    """
    Test 1: Discovery returns individual, relevant business profiles rather than article lists.
    """
    from backend.app.services.discovery_service import InstagramBusinessSearchProvider

    async def mock_search(self, niche, city_or_state="", keywords="", source_mode="instagram_only", limit=10):
        return [
            {
                "business_name": "Aura Luxury Boutique",
                "instagram_username": "auraboutique_kochi",
                "instagram_handle": "auraboutique_kochi",
                "instagram_url": "https://instagram.com/auraboutique_kochi",
                "website_url": "",
                "domain": "",
                "source_url": "https://instagram.com/auraboutique_kochi",
                "raw_title": "Aura Luxury Boutique (@auraboutique_kochi) • Instagram photos and videos",
                "snippet": "Designer ethnic wear & linen collection in Panampilly Nagar, Kochi. Order via WhatsApp +91 9846123456 or DM.",
                "contacts": {"phones": ["+919846123456"], "emails": [], "external_links": []}
            }
        ]

    monkeypatch.setattr(InstagramBusinessSearchProvider, "search", mock_search)

    resp = client.post("/api/leads/discover", json={
        "niche": "Clothing Boutiques",
        "city_or_state": "Kochi",
        "source_mode": "instagram_only"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert len(data["results"]) == 1
    item = data["results"][0]
    assert item["business_name"] == "Aura Luxury Boutique"
    assert item["instagram_username"] == "auraboutique_kochi"
    assert item["instagram_url"] == "https://instagram.com/auraboutique_kochi"
    assert "article" not in item["source_url"]


def test_invalid_and_irrelevant_search_results_excluded():
    """
    Test 2: Invalid or irrelevant search results (posts, reels, system pages, listicles) are excluded.
    """
    from backend.app.services.discovery_service import is_valid_instagram_profile_url

    # Posts, reels, stories, explore, and system URLs must be rejected
    assert is_valid_instagram_profile_url("https://www.instagram.com/p/C-1234567/")[0] is False
    assert is_valid_instagram_profile_url("https://www.instagram.com/reel/C-xyzabc/")[0] is False
    assert is_valid_instagram_profile_url("https://www.instagram.com/explore/tags/kochi/")[0] is False
    assert is_valid_instagram_profile_url("https://www.instagram.com/stories/highlights/")[0] is False
    assert is_valid_instagram_profile_url("https://www.instagram.com/accounts/login/")[0] is False
    assert is_valid_instagram_profile_url("https://www.instagram.com/popular/boutiques-kochi/")[0] is False

    # Valid profile URLs must be accepted and yield the username
    valid, user = is_valid_instagram_profile_url("https://www.instagram.com/kochi_boutiquee/")
    assert valid is True
    assert user == "kochi_boutiquee"


def test_profile_urls_and_evidence_are_verifiable():
    """
    Test 3: Profile URLs and evidence are real and verifiable (username extracted, title cleaned, contacts parsed).
    """
    from backend.app.services.discovery_service import clean_instagram_business_name, extract_contacts_and_links

    # Clean title extraction
    clean = clean_instagram_business_name("Malabar Roastery (@malabarroastery) • Instagram photos and videos", "malabarroastery")
    assert clean == "Malabar Roastery"

    # Contact extraction from bio snippet
    bio = "Specialty single-origin coffees. Panampilly Nagar, Kochi. WhatsApp: +91 9847112233 | inquiries@malabarroastery.in | wa.me/919847112233"
    contacts = extract_contacts_and_links(bio)
    assert "+919847112233" in contacts["phones"]
    assert "inquiries@malabarroastery.in" in contacts["emails"]


def test_fit_scores_reflect_evidence_instead_of_constant_score():
    """
    Test 4: Fit scores reflect evidence instead of a constant score.
    No-website and broken-website prospects receive higher fit scores than existing working sites.
    """
    from backend.app.services.discovery_service import evaluate_digital_opportunity

    # Case A: Instagram-only business taking orders via WhatsApp (Prime opportunity for Abenzo)
    eval_no_web = evaluate_digital_opportunity(
        business_name="Aura Boutique",
        niche="Boutiques",
        city="Kochi",
        website_url="",
        instagram_handle="auraboutique",
        snippet="Custom stitching and saree orders via WhatsApp in Kochi.",
        contacts={"phones": ["+919846000000"], "emails": [], "external_links": []}
    )

    # Case B: Business with existing working website
    eval_has_web = evaluate_digital_opportunity(
        business_name="Corporate Architects",
        niche="Architecture",
        city="Kochi",
        website_url="https://corporatearchitects.com",
        instagram_handle="corporatearch",
        snippet="Architecture and interior firm.",
        contacts={"phones": [], "emails": [], "external_links": []}
    )

    # Must reflect distinct scores based on genuine opportunity
    assert eval_no_web["lead_score"] != eval_has_web["lead_score"]
    assert eval_no_web["lead_score"] > eval_has_web["lead_score"]
    assert eval_no_web["website_status"] == "no_website"
    assert "no_website_opportunity" in eval_no_web["score_breakdown"]
    assert "WhatsApp" in eval_no_web["observed_problems"]


def test_existing_leads_not_duplicated_by_instagram_or_domain():
    """
    Test 5: Existing leads are not duplicated by normalized Instagram handle, website domain, or name.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        now = "2026-10-18T10:00:00"
        cursor.execute("""
            INSERT INTO leads (business_name, instagram_url, website_url, created_at, updated_at)
            VALUES ('Kochi Artisan Cafe', 'https://instagram.com/kochiartisancafe/', 'https://kochiartisancafe.in', ?, ?)
        """, (now, now))
        conn.commit()

        from backend.app.services.discovery_service import check_duplicate_lead

        # Match by instagram handle
        dup_ig = check_duplicate_lead(cursor, "Different Name", instagram_url="https://www.instagram.com/kochiartisancafe")
        assert dup_ig is not None
        assert dup_ig["matched_by"] == "instagram_handle"

        # Match by website domain
        dup_web = check_duplicate_lead(cursor, "Another Name", website_url="https://www.kochiartisancafe.in/menu")
        assert dup_web is not None
        assert dup_web["matched_by"] == "website_url"


def test_personalized_outreach_drafts_generated_and_can_be_copied():
    """
    Test 6: Outreach drafts are personalized, concise (30-50 words), non-spam, and reference observed facts.
    """
    from backend.app.services.discovery_service import evaluate_digital_opportunity

    eval_res = evaluate_digital_opportunity(
        business_name="The Leather Studio",
        niche="Handmade Bags",
        city="Kochi",
        website_url="",
        instagram_handle="theleatherstudio",
        snippet="Handcrafted leather bags in Panampilly Nagar, Kochi.",
        contacts={"phones": ["+919846123456"], "emails": [], "external_links": []}
    )

    draft = eval_res["personalized_dm"]
    assert len(draft.split()) >= 25
    assert len(draft.split()) <= 65
    assert "The Leather Studio" in draft or "@theleatherstudio" in draft
    assert "Kochi" in draft
    assert "WhatsApp" in draft or "orders" in draft


def test_crm_records_outreach_queue_statuses_and_timestamps():
    """
    Test 7: The CRM records statuses correctly: followed, contacted, replied, interested, converted, with action timestamps.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        now = "2026-10-18T10:00:00"
        cursor.execute("""
            INSERT INTO leads (business_name, outreach_status, created_at, updated_at)
            VALUES ('Outreach Queue Test Co', 'new', ?, ?)
        """, (now, now))
        lead_id = cursor.lastrowid
        conn.commit()

    # Update to 'followed'
    resp = client.patch(f"/api/leads/{lead_id}", json={"outreach_status": "followed"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["outreach_status"] == "followed"
    assert data["outreach_action_at"] != ""

    # Update to 'contacted'
    resp2 = client.patch(f"/api/leads/{lead_id}", json={"outreach_status": "contacted"})
    assert resp2.status_code == 200
    assert resp2.json()["outreach_status"] == "contacted"


def test_instagram_inbound_dm_matches_lead_and_updates_stage():
    """
    Test 8: Inbound Instagram DM matches existing CRM lead, links conversation, and marks lead as 'replied'.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        now = "2026-10-18T10:00:00"
        cursor.execute("""
            INSERT INTO leads (business_name, instagram_handle, outreach_status, created_at, updated_at)
            VALUES ('Studio Verde', 'studioverde_kochi', 'contacted', ?, ?)
        """, (now, now))
        lead_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO conversations (platform, external_thread_id, recipient_id, lead_id, contact_display_name, created_at, updated_at)
            VALUES ('instagram', 'ig_sender_verde_100', 'ig_sender_verde_100', ?, 'Studio Verde', ?, ?)
        """, (lead_id, now, now))
        conn.commit()

    # Inbound webhook payload from this customer
    webhook_payload = {
        "entry": [{
            "messaging": [{
                "sender": {"id": "ig_sender_verde_100"},
                "message": {
                    "mid": "mid_inbound_verde_001",
                    "text": "Hi Abenzo! Yes, we would love to see a preview of the WhatsApp catalog."
                }
            }]
        }]
    }

    resp = client.post("/api/meta/webhook", json=webhook_payload)
    assert resp.status_code == 200

    # Verify that the lead's status in CRM is now 'replied'
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT outreach_status, outreach_action_at FROM leads WHERE id = ?", (lead_id,))
        row = cursor.fetchone()
        assert row["outreach_status"] == "replied"
        assert row["outreach_action_at"] != ""


def test_contact_details_captured_via_consent_aware_workflow():
    """
    Test 9: Contact details and qualification fields (timeline, budget, consent source) are stored accurately.
    """
    create_payload = {
        "business_name": "Kochi Gourmet Spices",
        "city": "Kochi",
        "state": "Kerala",
        "contact_name": "Arun Kumar",
        "public_phone": "+91 9846012345",
        "public_email": "arun@kochispices.in",
        "project_timeline": "3 weeks",
        "budget": "₹45,000",
        "consent_source": "Voluntary Direct Message"
    }

    resp = client.post("/api/leads", json=create_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["contact_name"] == "Arun Kumar"
    assert data["public_phone"] == "+91 9846012345"
    assert data["public_email"] == "arun@kochispices.in"
    assert data["project_timeline"] == "3 weeks"
    assert data["budget"] == "₹45,000"
    assert data["consent_source"] == "Voluntary Direct Message"


def test_search_provider_limitations_shown_honestly_without_fabrication(monkeypatch):
    """
    Test 10: When a search provider returns no results or encounters an error,
    it returns an honest limitation notice instead of fabricating fake accounts or phone numbers.
    """
    from backend.app.services.discovery_service import InstagramBusinessSearchProvider

    async def mock_empty_search(self, *args, **kwargs):
        return []

    monkeypatch.setattr(InstagramBusinessSearchProvider, "search", mock_empty_search)

    resp = client.post("/api/leads/discover", json={
        "niche": "VeryObscureNicheXYZ",
        "city_or_state": "RemoteTown",
        "source_mode": "instagram_only"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["total_found"] == 0
    assert len(data["results"]) == 0
    assert data["limitation_notice"] is not None
    assert "0 verified profiles" in data["limitation_notice"]


def test_regression_successful_results_with_valid_instagram_business_profiles(monkeypatch):
    """
    Regression Test 1: Successful results containing valid Instagram business profiles.
    Verifies that valid profiles are parsed, verified, scored, and returned with diagnostics.
    """
    from backend.app.services.discovery_service import DuckDuckGoSearchProvider

    mock_raw_items = [
        {
            "raw_title": "Kirthi The Boutique (@kirthi_kochi) • Instagram photos and videos",
            "target_url": "https://www.instagram.com/kirthi_kochi/",
            "snippet": "Designer wear, bridal couture, custom stitching in Panampilly Nagar, Kochi. WhatsApp: +91 9847112233"
        },
        {
            "raw_title": "S.H.E Boutique (@s.h.e_designer) • Instagram photos and videos",
            "target_url": "https://instagram.com/s.h.e_designer",
            "snippet": "Handcrafted sarees and kurthis in Kochi, Kerala. Inquiries via DM or WhatsApp: +91 9846001122"
        }
    ]

    async def mock_ddg_search(self, queries, limit, source_mode, diagnostics):
        diagnostics["queries_executed"].extend(queries)
        diagnostics["raw_results_count"] += len(mock_raw_items)
        return mock_raw_items

    monkeypatch.setattr(DuckDuckGoSearchProvider, "search", mock_ddg_search)

    resp = client.post("/api/leads/discover", json={
        "niche": "clothing boutiques",
        "city_or_state": "kochi, kerala",
        "source_mode": "instagram_only"
    })

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["total_found"] == 2
    assert len(data["results"]) == 2

    first = data["results"][0]
    assert first["business_name"] == "Kirthi The Boutique"
    assert first["instagram_username"] == "kirthi_kochi"
    assert first["instagram_url"] == "https://instagram.com/kirthi_kochi"
    assert "+919847112233" in first["contact_details"]
    assert first["website_status"] == "no_website"
    assert first["lead_score"] >= 65

    # Structured diagnostics verified
    diag = data["diagnostics"]
    assert diag is not None
    assert diag["valid_profiles_count"] == 2
    assert diag["raw_results_count"] == 2
    assert len(diag["queries_executed"]) >= 1


def test_regression_url_normalization_and_valid_profile_acceptance():
    """
    Regression Test 2: URL normalization and valid profile acceptance.
    Verifies location normalizer and profile classifier with standard and www formats.
    """
    from backend.app.services.discovery_service import (
        normalize_location_input,
        classify_instagram_url,
        is_valid_instagram_profile_url
    )

    # Location normalization
    loc_kerala = normalize_location_input("kerala")
    assert loc_kerala["city"] == ""
    assert loc_kerala["state"] == "Kerala"

    loc_india_suffix = normalize_location_input("Kerala, India")
    assert loc_india_suffix["city"] == ""
    assert loc_india_suffix["state"] == "Kerala"

    loc_kochi_compound = normalize_location_input("kochi, kerala")
    assert loc_kochi_compound["city"] == "Kochi"
    assert loc_kochi_compound["state"] == "Kerala"
    assert "Cochin" in loc_kochi_compound["aliases"]

    loc_city_only = normalize_location_input("Kochi")
    assert loc_city_only["city"] == "Kochi"
    assert loc_city_only["state"] == "Kerala"

    # URL normalization and validation (standard + www + parameters + trailing slashes)
    test_urls = [
        ("https://instagram.com/myboutique", "myboutique"),
        ("https://www.instagram.com/myboutique/", "myboutique"),
        ("https://www.instagram.com/my_boutique_official/?hl=en", "my_boutique_official"),
        ("http://instagram.com/my.boutique", "my.boutique"),
    ]
    for url, expected_user in test_urls:
        valid, user, reason = classify_instagram_url(url)
        assert valid is True
        assert user == expected_user
        assert reason == ""

        # Backward compatibility 2-tuple function
        v2, u2 = is_valid_instagram_profile_url(url)
        assert v2 is True
        assert u2 == expected_user


def test_regression_rejection_of_posts_reels_and_irrelevant_articles():
    """
    Regression Test 3: Rejection of posts, reels, popular pages, directories, and irrelevant articles.
    """
    from backend.app.services.discovery_service import (
        classify_instagram_url,
        extract_root_domain,
        AGGREGATOR_LISTICLE_DOMAINS,
        LISTICLE_TITLE_PATTERNS
    )
    import re

    # Non-profile Instagram URLs must be rejected with 'reserved_path'
    rejected_urls = [
        "https://www.instagram.com/p/DF7654321/",
        "https://www.instagram.com/reel/C89abcde/",
        "https://www.instagram.com/reels/fashion/",
        "https://www.instagram.com/stories/daily_updates/",
        "https://www.instagram.com/explore/tags/kochiboutique/",
        "https://www.instagram.com/popular/best-boutiques-in-kochi/",
        "https://www.instagram.com/directory/profiles/",
        "https://www.instagram.com/accounts/login/",
        "https://www.instagram.com/about/jobs/",
    ]
    for u in rejected_urls:
        valid, _, reason = classify_instagram_url(u)
        assert valid is False
        assert reason == "reserved_path"

    # Listicle and aggregator rejection
    assert extract_root_domain("https://www.tripadvisor.in/Attractions-g297633.html") in AGGREGATOR_LISTICLE_DOMAINS
    assert extract_root_domain("https://www.justdial.com/Kochi/Boutiques") in AGGREGATOR_LISTICLE_DOMAINS
    assert extract_root_domain("https://dir.indiamart.com/kochi/boutique.html") in AGGREGATOR_LISTICLE_DOMAINS

    listicle_titles = [
        "Top 10 Best Boutiques in Kochi (2026 Guide)",
        "15 Best Boutiques in Kerala for Wedding Shopping",
        "List of Wholesale Suppliers and Boutiques in Ernakulam"
    ]
    for title in listicle_titles:
        assert any(re.search(pat, title.lower()) for pat in LISTICLE_TITLE_PATTERNS)


def test_regression_provider_failure_and_fallback_behavior(monkeypatch):
    """
    Regression Test 4: Provider failure and fallback behavior.
    - When DuckDuckGo returns 202 bot challenge, records rate_limited_202 and rate_limits count.
    - Seamlessly falls back to configured secondary provider (Serper).
    """
    from backend.app.services.discovery_service import DuckDuckGoSearchProvider, SerperSearchProvider

    # 1. DuckDuckGo 202 rate-limited without secondary key
    async def mock_ddg_202(self, queries, limit, source_mode, diagnostics):
        diagnostics["queries_executed"].extend(queries)
        diagnostics["rate_limits"] += 1
        diagnostics["provider_status"] = "rate_limited_202"
        diagnostics["provider_error_message"] = "DuckDuckGo returned HTTP 202 Bot Challenge from this server IP."
        return []

    monkeypatch.setattr(DuckDuckGoSearchProvider, "search", mock_ddg_202)
    monkeypatch.setattr("backend.app.config.settings.SERPER_API_KEY", "")
    monkeypatch.setattr("backend.app.config.settings.TAVILY_API_KEY", "")
    monkeypatch.setattr("backend.app.config.settings.BRAVE_SEARCH_API_KEY", "")
    monkeypatch.setattr("backend.app.config.settings.SERPAPI_API_KEY", "")

    resp = client.post("/api/leads/discover", json={
        "niche": "startups",
        "city_or_state": "kerala",
        "source_mode": "instagram_only"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_found"] == 0
    assert data["diagnostics"]["rate_limits"] >= 1
    assert data["diagnostics"]["provider_status"] == "rate_limited_202"
    assert "HTTP 202 Bot Challenge" in data["limitation_notice"]

    # 2. DuckDuckGo 202 triggers fallback to configured Serper API
    monkeypatch.setattr("backend.app.config.settings.SERPER_API_KEY", "dummy_serper_key_123")

    mock_serper_items = [
        {
            "raw_title": "Kerala Tech Startup (@keralastartuphub) • Instagram",
            "target_url": "https://www.instagram.com/keralastartuphub/",
            "snippet": "Empowering early-stage startups in Kochi, Kerala. Inquiries: contact@keralastartup.in"
        }
    ]

    async def mock_serper_search(self, queries, limit, source_mode, diagnostics):
        diagnostics["queries_executed"].extend(queries)
        diagnostics["raw_results_count"] += len(mock_serper_items)
        return mock_serper_items

    monkeypatch.setattr(SerperSearchProvider, "search", mock_serper_search)

    resp_fb = client.post("/api/leads/discover", json={
        "niche": "startups",
        "city_or_state": "kerala",
        "source_mode": "instagram_only"
    })
    assert resp_fb.status_code == 200
    data_fb = resp_fb.json()
    assert data_fb["total_found"] == 1
    assert data_fb["results"][0]["instagram_username"] == "keralastartuphub"
    assert data_fb["diagnostics"]["fallback_used"] is True
    assert data_fb["diagnostics"]["provider_used"] == "Google (Serper API)"


def test_regression_deduplication_and_empty_results(monkeypatch):
    """
    Regression Test 5: Deduplication across results and existing CRM records, and clean empty handling.
    """
    from backend.app.services.discovery_service import DuckDuckGoSearchProvider

    # Pre-populate CRM with an existing lead
    with get_db() as conn:
        cursor = conn.cursor()
        now = "2026-10-18T10:00:00"
        cursor.execute("""
            INSERT INTO leads (business_name, instagram_url, instagram_handle, created_at, updated_at)
            VALUES ('Existing Boutique', 'https://instagram.com/existing_boutique', 'existing_boutique', ?, ?)
        """, (now, now))
        conn.commit()

    # Provider returns: 1 duplicate in CRM, 1 internal duplicate, and 1 fresh prospect
    mock_items = [
        {
            "raw_title": "Existing Boutique (@existing_boutique)",
            "target_url": "https://www.instagram.com/existing_boutique/",
            "snippet": "Existing shop in Kochi"
        },
        {
            "raw_title": "Fresh Boutique (@fresh_boutique_kochi)",
            "target_url": "https://www.instagram.com/fresh_boutique_kochi/",
            "snippet": "New handcrafted fashion store in Kochi"
        },
        {
            "raw_title": "Fresh Boutique Copy (@fresh_boutique_kochi)",
            "target_url": "https://www.instagram.com/fresh_boutique_kochi/?hl=en",
            "snippet": "Duplicate entry"
        }
    ]

    async def mock_search(self, queries, limit, source_mode, diagnostics):
        diagnostics["queries_executed"].extend(queries)
        diagnostics["raw_results_count"] += len(mock_items)
        return mock_items

    monkeypatch.setattr(DuckDuckGoSearchProvider, "search", mock_search)

    # Search with exclude_crm=True
    resp = client.post("/api/leads/discover", json={
        "niche": "boutiques",
        "city_or_state": "kochi",
        "source_mode": "instagram_only",
        "exclude_crm": True
    })

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_found"] == 1
    assert data["results"][0]["instagram_username"] == "fresh_boutique_kochi"
    # Duplicates removed must be at least 2 (1 internal duplicate + 1 CRM duplicate)
    assert data["diagnostics"]["duplicates_removed"] >= 2


def test_serper_primary_provider_selection_and_diagnostics(monkeypatch):
    """
    Verifies that:
    1. SEARCH_PROVIDER=serper selects Serper as the primary provider.
    2. key_configured is True (boolean only) when SERPER_API_KEY is present, False when unset.
    3. safe diagnostics show selected_provider, key_configured, provider_request_status, raw_results_count.
    4. SERPER_API_KEY is never exposed in response.
    """
    import os
    from backend.app.services.discovery_service import SerperSearchProvider, DuckDuckGoSearchProvider

    secret_key = "secret_serper_test_token_999"
    monkeypatch.setenv("SEARCH_PROVIDER", "serper")
    monkeypatch.setenv("SERPER_API_KEY", secret_key)

    mock_items = [
        {
            "raw_title": "Boutique Serper (@boutique_serper) • Instagram photos and videos",
            "target_url": "https://www.instagram.com/boutique_serper/",
            "snippet": "Clothing boutique in Kochi, Kerala. Call: 9876543210"
        }
    ]

    ddg_called = []
    async def mock_ddg_search(self, queries, limit, source_mode, diagnostics):
        ddg_called.append(True)
        return []

    serper_calls = []
    async def mock_serper_search(self, queries, limit, source_mode, diagnostics):
        serper_calls.append(queries)
        diagnostics["queries_executed"].extend(queries)
        diagnostics["raw_results_count"] += len(mock_items)
        diagnostics["provider_request_status"] = "HTTP 200 OK"
        return mock_items

    monkeypatch.setattr(DuckDuckGoSearchProvider, "search", mock_ddg_search)
    monkeypatch.setattr(SerperSearchProvider, "search", mock_serper_search)

    resp = client.post("/api/leads/discover", json={
        "niche": "clothing",
        "city_or_state": "kochi",
        "source_mode": "instagram_only"
    })

    assert resp.status_code == 200
    data = resp.json()
    assert len(serper_calls) == 1
    assert len(ddg_called) == 0  # DuckDuckGo should NOT be called since Serper was primary

    diag = data["diagnostics"]
    assert diag["selected_provider"] == "Google (Serper API)"
    assert diag["key_configured"] is True  # Boolean only!
    assert isinstance(diag["key_configured"], bool)
    assert diag["provider_request_status"] == "HTTP 200 OK"
    assert diag["raw_results_count"] == 1
    assert data["total_found"] == 1
    assert data["results"][0]["instagram_username"] == "boutique_serper"

    # Verify secret key is never leaked
    resp_text = resp.text
    assert secret_key not in resp_text


def test_auto_provider_ddg_202_fallback_to_serper_and_diagnostics(monkeypatch):
    """
    Verifies that:
    1. In SEARCH_PROVIDER=auto, DuckDuckGo is primary.
    2. On HTTP 202 bot challenge, DuckDuckGo is not retried indefinitely.
    3. Provider automatically falls back to Serper when key is configured.
    4. Diagnostics report fallback_attempts and updated provider status safely.
    """
    from backend.app.services.discovery_service import DuckDuckGoSearchProvider, SerperSearchProvider

    monkeypatch.setenv("SEARCH_PROVIDER", "auto")
    monkeypatch.setenv("SERPER_API_KEY", "serper_live_mock_key")

    ddg_query_count = []
    async def mock_ddg_challenge(self, queries, limit, source_mode, diagnostics):
        for q in queries:
            ddg_query_count.append(q)
            diagnostics["queries_executed"].append(q)
            diagnostics["rate_limits"] += 1
            diagnostics["provider_status"] = "rate_limited_202"
            diagnostics["provider_request_status"] = "HTTP 202 Bot Challenge"
            diagnostics["provider_error_message"] = "DuckDuckGo returned HTTP 202 Bot Challenge from this server IP."
            break  # Break immediately on 202 (never retry indefinitely)
        return []

    mock_fallback_items = [
        {
            "raw_title": "Café Kochi Roastery (@cafekochi_roastery)",
            "target_url": "https://www.instagram.com/cafekochi_roastery/",
            "snippet": "Artisanal coffee and roastery in Kochi, Kerala. WhatsApp orders."
        }
    ]

    serper_query_count = []
    async def mock_serper_search(self, queries, limit, source_mode, diagnostics):
        serper_query_count.append(queries)
        diagnostics["queries_executed"].extend(queries)
        diagnostics["raw_results_count"] += len(mock_fallback_items)
        diagnostics["provider_request_status"] = "HTTP 200 OK"
        return mock_fallback_items

    monkeypatch.setattr(DuckDuckGoSearchProvider, "search", mock_ddg_challenge)
    monkeypatch.setattr(SerperSearchProvider, "search", mock_serper_search)

    resp = client.post("/api/leads/discover", json={
        "niche": "cafe",
        "city_or_state": "kochi",
        "source_mode": "instagram_only"
    })

    assert resp.status_code == 200
    data = resp.json()

    # DuckDuckGo broke immediately on first query
    assert len(ddg_query_count) == 1
    # Serper was called as fallback
    assert len(serper_query_count) == 1

    diag = data["diagnostics"]
    assert diag["fallback_used"] is True
    assert diag["selected_provider"] == "Google (Serper API)"
    assert diag["key_configured"] is True
    assert isinstance(diag["key_configured"], bool)
    assert diag["provider_request_status"] == "HTTP 200 OK"
    assert diag["raw_results_count"] == 1
    assert any("HTTP 202" in attempt for attempt in diag["fallback_attempts"])
    assert any("Google (Serper API): Success" in attempt for attempt in diag["fallback_attempts"])

    assert data["total_found"] == 1
    assert data["results"][0]["instagram_username"] == "cafekochi_roastery"


def test_api_key_security_never_logged_or_exposed(monkeypatch):
    """
    Verifies that key_configured is strictly boolean and API keys are never exposed in JSON output.
    """
    super_secret_key = "serper_super_secret_value_xyz789"
    monkeypatch.setenv("SEARCH_PROVIDER", "serper")
    monkeypatch.setenv("SERPER_API_KEY", super_secret_key)

    resp = client.post("/api/leads/discover", json={
        "niche": "bakeries",
        "city_or_state": "kochi",
        "search_provider": "serper"
    })
    assert resp.status_code == 200
    # Must never contain super_secret_key anywhere in response body
    assert super_secret_key not in resp.text
    data = resp.json()
    assert isinstance(data["diagnostics"]["key_configured"], bool)







