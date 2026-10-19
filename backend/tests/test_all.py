import pytest
import sqlite3
import json
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

    async def mock_draft_routine(incoming, history, profile):
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
        cursor.execute("SELECT * FROM conversation_events WHERE external_event_id = 'mid_auto_routine_001'")
        ev = dict(cursor.fetchone())
        assert ev["delivery_status"] == "sent"
        assert ev["meta_message_id"] == "mid_auto_1"
        assert ev["approved_text"] == "Abenzo Starter Package starts at ₹15,000+ for 3-5 pages."

        cursor.execute("SELECT needs_human FROM conversations WHERE external_thread_id = 'ig_user_auto_routine_1'")
        assert cursor.fetchone()["needs_human"] == 0

    # 3. Complex inquiry requiring human decision
    async def mock_draft_complex(incoming, history, profile):
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
        assert ev["delivery_status"] == "draft_pending"
        assert ev["approved_text"] == ""

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
    async def mock_draft(incoming, history, profile):
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




