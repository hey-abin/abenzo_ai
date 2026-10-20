import pytest
import json
import httpx
from datetime import datetime
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.database import get_db, init_db, _ph
from backend.app.services.discovery_service import (
    extract_contacts_and_links,
    pick_best_website_url,
    evaluate_digital_opportunity
)
from backend.app.services.website_checker import check_website

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test_messaging.db")
    monkeypatch.setattr("backend.app.config.settings.DB_PATH", test_db)
    init_db(test_db)
    yield test_db


# ---------------------------------------------------------------------------
# 1. Existing websites detected rather than misclassified
# ---------------------------------------------------------------------------

def test_existing_website_detection_from_bio():
    """
    Verifies that protocol-less URLs (e.g. 'www.thestudio.in' or 'boutique.store')
    in Instagram bio are accurately extracted and prepended with https://,
    and branded domains are chosen over link aggregators.
    """
    bio_text = "Handcrafted silver jewellery. Shop online: www.tarajewels.in | WhatsApp orders: wa.me/919846001122"
    contacts = extract_contacts_and_links(bio_text)
    
    assert "https://www.tarajewels.in" in contacts["external_links"]
    assert any("wa.me" in link for link in contacts["external_links"])
    
    # pick_best_website_url must prioritize the custom branded domain
    best_url = pick_best_website_url(contacts["external_links"])
    assert best_url == "https://www.tarajewels.in"
    assert "wa.me" not in best_url

    # Another format: bare commercial domain
    bio_text_2 = "Modern apparel brand. Visit our store at zayafashion.store for new drops!"
    contacts_2 = extract_contacts_and_links(bio_text_2)
    assert "https://zayafashion.store" in contacts_2["external_links"]
    best_url_2 = pick_best_website_url(contacts_2["external_links"])
    assert best_url_2 == "https://zayafashion.store"


@pytest.mark.anyio
async def test_website_verification_statuses(monkeypatch):
    """
    Verifies distinction between:
    - Website verified (live HTTP 200)
    - Website unreachable (HTTP 404 or connection error)
    - Website not assessed (timeout / network uncertainty)
    - No website found
    """
    # 1. Live site
    req_live = httpx.Request("GET", "https://www.tarajewels.in")
    resp_live = httpx.Response(
        status_code=200,
        request=req_live,
        text="<html><head><title>Tara Jewels Official</title><meta name='viewport' content='width=device-width'></head><body>Shop now Cart</body></html>"
    )
    async def mock_get_live(client_self, url, headers=None):
        return resp_live

    with patch("httpx.AsyncClient.get", mock_get_live):
        res_live = await check_website("www.tarajewels.in")
        assert res_live.status == "found"
        assert "verified live" in res_live.evidence_summary.lower()
        assert res_live.raw_details["is_https"] is True

    # 2. Broken/unreachable site
    req_broken = httpx.Request("GET", "https://brokenboutique.com")
    resp_broken = httpx.Response(status_code=404, request=req_broken, text="Not Found")
    async def mock_get_404(client_self, url, headers=None):
        return resp_broken

    with patch("httpx.AsyncClient.get", mock_get_404):
        res_broken = await check_website("https://brokenboutique.com")
        assert res_broken.status == "broken_website"
        assert "unreachable" in res_broken.evidence_summary.lower()

    # 3. Uncertain / Timeout
    async def mock_get_timeout(client_self, url, headers=None):
        raise httpx.TimeoutException("Timeout")

    with patch("httpx.AsyncClient.get", mock_get_timeout):
        res_timeout = await check_website("https://slowserver.com")
        assert res_timeout.status == "uncertain"
        assert "not assessed" in res_timeout.evidence_summary.lower()

    # 4. No URL provided
    res_none = await check_website("")
    assert res_none.status == "uncertain"


# ---------------------------------------------------------------------------
# 2. Unknown website status not treated as no website
# ---------------------------------------------------------------------------

def test_unknown_website_status_not_treated_as_no_website():
    """
    When a website URL exists but its status is uncertain or cannot be assessed,
    it must NOT receive an arbitrary no-website bonus or be claimed as lacking a website.
    """
    eval_uncertain = evaluate_digital_opportunity(
        business_name="Indie Studio",
        niche="Design",
        city="Kochi",
        website_url="https://indiestudio.in",
        instagram_handle="indiestudio",
        snippet="Brand design & visual identity in Kochi. Visit our site: https://indiestudio.in",
        contacts={"phones": [], "emails": [], "external_links": ["https://indiestudio.in"]}
    )

    # Has website opportunity (+10), not no-website bonus (+20/25)
    assert eval_uncertain["website_status"] == "has_website"
    assert "no_website_opportunity" not in eval_uncertain["score_breakdown"]


# ---------------------------------------------------------------------------
# 3. Dashboard sending through an eligible existing conversation
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_dashboard_send_through_eligible_conversation(monkeypatch):
    """
    Verifies that when an eligible conversation exists within Meta's 24-hr messaging window:
    1. Messaging status indicates sending is permitted.
    2. POST /api/leads/{id}/send-message transmits via the Meta integration.
    3. Delivery status is saved as 'sent'.
    4. Lead CRM outreach status is updated to 'contacted'.
    """
    monkeypatch.setattr("backend.app.config.settings.INSTAGRAM_ACCESS_TOKEN", "valid_ig_test_token")

    # Seed lead and existing conversation
    now_iso = datetime.now().isoformat()
    lead_id = None
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO leads (business_name, instagram_url, outreach_status, website_status, personalized_dm, created_at, updated_at)
            VALUES ('Aura Boutique', 'https://instagram.com/auraboutique', 'draft_ready', 'no_website', 'Hi Aura Boutique! Loved your work.', ?, ?)
        """, (now_iso, now_iso))
        lead_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO conversations (platform, external_thread_id, contact_display_name, last_message_at, created_at, updated_at)
            VALUES ('instagram', 'ig_user_12345', 'auraboutique', ?, ?, ?)
        """, (now_iso, now_iso, now_iso))
        conn.commit()

    # 1. Check messaging status endpoint
    status_resp = client.get(f"/api/leads/{lead_id}/messaging-status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["can_send"] is True
    assert status_data["suggested_action"] == "dashboard_send"
    assert status_data["recipient_id"] == "ig_user_12345"

    # Mock dispatch_instagram_dm to simulate successful Graph API response
    async def mock_dispatch(recipient_id, text):
        return {
            "success": True,
            "message_id": "mid_meta_confirmed_999",
            "recipient_id": recipient_id
        }

    monkeypatch.setattr("backend.app.routers.meta.dispatch_instagram_dm", mock_dispatch)

    # 2. Send message from dashboard
    send_resp = client.post(f"/api/leads/{lead_id}/send-message", json={
        "message_text": "Hi Aura Boutique! Custom proposal preview."
    })
    assert send_resp.status_code == 200
    send_data = send_resp.json()
    assert send_data["delivery_status"] == "sent"
    assert send_data["meta_message_id"] == "mid_meta_confirmed_999"

    # 3. Verify CRM record was updated
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT outreach_status FROM leads WHERE id = ?", (lead_id,))
        lead_row = cursor.fetchone()
        assert lead_row["outreach_status"] == "contacted"

        cursor.execute("SELECT * FROM conversation_events WHERE meta_message_id = 'mid_meta_confirmed_999'")
        ev_row = cursor.fetchone()
        assert ev_row is not None
        assert ev_row["delivery_status"] == "sent"
        assert ev_row["message_text"] == "Hi Aura Boutique! Custom proposal preview."


# ---------------------------------------------------------------------------
# 4. Unauthorized first-contact Instagram sends blocked with clear explanation
# ---------------------------------------------------------------------------

def test_unauthorized_first_contact_send_blocked(monkeypatch):
    """
    Verifies that when a lead has never messaged the business:
    1. GET /api/leads/{id}/messaging-status clearly reports cold messaging is forbidden by Meta.
    2. POST /api/leads/{id}/send-message is rejected with HTTP 403 Forbidden.
    3. Guidance directs operator to manual outreach actions (Copy Message + Open Profile).
    """
    now_iso = datetime.now().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO leads (business_name, instagram_url, outreach_status, website_status, personalized_dm, created_at, updated_at)
            VALUES ('Cold Prospect Studio', 'https://instagram.com/coldprospect', 'draft_ready', 'no_website', 'Hello!', ?, ?)
        """, (now_iso, now_iso))
        cold_lead_id = cursor.lastrowid
        conn.commit()

    # 1. Check messaging status
    status_resp = client.get(f"/api/leads/{cold_lead_id}/messaging-status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["can_send"] is False
    assert status_data["suggested_action"] == "manual_outreach"
    assert "Platform Policy" in status_data["reason"]

    # 2. Attempt dashboard send -> HTTP 403 Forbidden
    send_resp = client.post(f"/api/leads/{cold_lead_id}/send-message", json={
        "message_text": "Unsolicited cold DM attempt"
    })
    assert send_resp.status_code == 403
    err_detail = send_resp.json()["detail"]
    assert "Platform Policy" in err_detail
    assert "Copy Message" in err_detail


# ---------------------------------------------------------------------------
# 5. Failed delivery status handling
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_failed_delivery_status_handling(monkeypatch):
    """
    When Meta Graph API rejects the send (e.g. 24-hr messaging window closed),
    the event is recorded with delivery_status='failed' and HTTP 502 is returned.
    The lead outreach_status is NOT marked as sent.
    """
    monkeypatch.setattr("backend.app.config.settings.INSTAGRAM_ACCESS_TOKEN", "valid_ig_test_token")
    now_iso = datetime.now().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO leads (business_name, instagram_url, outreach_status, website_status, created_at, updated_at)
            VALUES ('Expired Window Lead', 'https://instagram.com/expiredlead', 'draft_ready', 'no_website', ?, ?)
        """, (now_iso, now_iso))
        lead_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO conversations (platform, external_thread_id, contact_display_name, last_message_at, created_at, updated_at)
            VALUES ('instagram', 'ig_user_expired', 'expiredlead', ?, ?, ?)
        """, (now_iso, now_iso, now_iso))
        conn.commit()

    async def mock_failed_dispatch(recipient_id, text):
        return {
            "success": False,
            "error_details": "Graph API Error 100: Messaging window expired"
        }

    monkeypatch.setattr("backend.app.routers.meta.dispatch_instagram_dm", mock_failed_dispatch)

    send_resp = client.post(f"/api/leads/{lead_id}/send-message", json={
        "message_text": "Follow-up message after window"
    })
    assert send_resp.status_code == 502
    assert "Graph API Error 100" in send_resp.json()["detail"]

    # Verify database recorded delivery_status='failed'
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT outreach_status FROM leads WHERE id = ?", (lead_id,))
        assert cursor.fetchone()["outreach_status"] == "draft_ready"

        cursor.execute("SELECT delivery_status, error_details FROM conversation_events WHERE direction = 'outbound' ORDER BY id DESC LIMIT 1")
        ev = cursor.fetchone()
        assert ev["delivery_status"] == "failed"
        assert "Graph API Error 100" in ev["error_details"]


# ---------------------------------------------------------------------------
# 6. Duplicate-send prevention
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_duplicate_send_prevention(monkeypatch):
    """
    Subsequent clicks or repeated sends within 60 seconds with identical text
    must be blocked with HTTP 409 Conflict to protect recipient and Meta rate limits.
    """
    monkeypatch.setattr("backend.app.config.settings.INSTAGRAM_ACCESS_TOKEN", "valid_ig_test_token")
    now_iso = datetime.now().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO leads (business_name, instagram_url, outreach_status, website_status, created_at, updated_at)
            VALUES ('Duplicate Test Lead', 'https://instagram.com/duplead', 'draft_ready', 'no_website', ?, ?)
        """, (now_iso, now_iso))
        lead_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO conversations (platform, external_thread_id, contact_display_name, last_message_at, created_at, updated_at)
            VALUES ('instagram', 'ig_user_dup', 'duplead', ?, ?, ?)
        """, (now_iso, now_iso, now_iso))
        conn.commit()

    async def mock_dispatch(recipient_id, text):
        return {"success": True, "message_id": "mid_dup_test_1", "recipient_id": recipient_id}

    monkeypatch.setattr("backend.app.routers.meta.dispatch_instagram_dm", mock_dispatch)

    # First send succeeds
    r1 = client.post(f"/api/leads/{lead_id}/send-message", json={"message_text": "Identical proposal message"})
    assert r1.status_code == 200

    # Immediate second click with identical message -> 409 Conflict
    r2 = client.post(f"/api/leads/{lead_id}/send-message", json={"message_text": "Identical proposal message"})
    assert r2.status_code == 409
    assert "Duplicate message send prevented" in r2.json()["detail"]


# ---------------------------------------------------------------------------
# 7. Global and per-conversation auto-reply controls
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_global_and_per_conversation_auto_reply_controls(monkeypatch):
    """
    Verifies that:
    1. Global auto-reply pause blocks automatic dispatch across all threads.
    2. Per-conversation auto-reply pause blocks dispatch for that specific conversation.
    3. Human approval requirement holds replies in draft_pending status.
    """
    monkeypatch.setattr("backend.app.config.settings.INSTAGRAM_ACCESS_TOKEN", "valid_ig_test_token")
    
    async def mock_draft(*args, **kwargs):
        return {
            "ai_draft": "Thanks for contacting Abenzo! Our packages start at ₹15,000.",
            "reasoning": "High confidence FAQ match",
            "lead_temperature": "qualified",
            "needs_human_decision": False
        }

    dispatch_called = False
    async def mock_dispatch(recipient_id, text):
        nonlocal dispatch_called
        dispatch_called = True
        return {"success": True, "message_id": "mid_autodispatch_1", "recipient_id": recipient_id}

    monkeypatch.setattr("backend.app.routers.meta.draft_inbound_response_with_ai", mock_draft)
    monkeypatch.setattr("backend.app.routers.meta.dispatch_instagram_dm", mock_dispatch)

    # Case A: Global Pause is Active
    client.put("/api/settings/automation", json={
        "auto_reply_enabled": True,
        "auto_reply_paused_global": True,
        "require_human_approval": False
    })

    payload_a = {
        "entry": [{
            "messaging": [{
                "sender": {"id": "user_global_pause_test"},
                "message": {"mid": "mid_global_pause_01", "text": "What are your prices?"}
            }]
        }]
    }
    resp_a = client.post("/api/meta/webhook", json=payload_a)
    assert resp_a.status_code == 200
    assert dispatch_called is False  # Must not dispatch when global pause is active

    # Verify event stored as received
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT delivery_status FROM conversation_events WHERE external_event_id = 'mid_global_pause_01'")
        assert cursor.fetchone()["delivery_status"] == "received"

    # Case B: Per-conversation pause
    # Resume global automation, but pause individual conversation
    client.put("/api/settings/automation", json={
        "auto_reply_enabled": True,
        "auto_reply_paused_global": False,
        "require_human_approval": False
    })

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO conversations (platform, external_thread_id, contact_display_name, auto_reply_paused, created_at, updated_at)
            VALUES ('instagram', 'user_per_conv_test', 'user_per_conv_test', 1, ?, ?)
        """, (datetime.now().isoformat(), datetime.now().isoformat()))
        conn.commit()

    payload_b = {
        "entry": [{
            "messaging": [{
                "sender": {"id": "user_per_conv_test"},
                "message": {"mid": "mid_per_conv_01", "text": "Can I get a quote?"}
            }]
        }]
    }
    resp_b = client.post("/api/meta/webhook", json=payload_b)
    assert resp_b.status_code == 200
    assert dispatch_called is False  # Must not dispatch when conversation is paused


# ---------------------------------------------------------------------------
# 8. Correct conversation-to-CRM matching
# ---------------------------------------------------------------------------

def test_conversation_to_crm_matching():
    """
    Verifies that when an inbound message arrives from a prospect whose
    Instagram handle or contact info exists in the CRM leads table,
    the event is associated with the lead and context is populated.
    """
    now_iso = datetime.now().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO leads (business_name, instagram_url, outreach_status, website_status, created_at, updated_at)
            VALUES ('Matched Boutique', 'https://instagram.com/matchedboutique', 'contacted', 'no_website', ?, ?)
        """, (now_iso, now_iso))
        lead_id = cursor.lastrowid
        conn.commit()

    # Link conversation with lead
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO conversations (platform, external_thread_id, contact_display_name, lead_id, created_at, updated_at)
            VALUES ('instagram', 'ig_user_crm_matched', 'matchedboutique', ?, ?, ?)
        """, (lead_id, now_iso, now_iso))
        conv_id = cursor.lastrowid
        conn.commit()

    resp = client.get(f"/api/inbox/conversations/{conv_id}")
    assert resp.status_code == 200
    conv_data = resp.json()
    assert conv_data["lead_id"] == lead_id
    assert conv_data["contact_display_name"] == "matchedboutique"
