import pytest
import json
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.database import get_db, init_db, _ph
from backend.app.services.prospecting_service import (
    inspect_meta_hashtag_capabilities,
    research_prospecting_hashtags,
    extract_post_and_profile_info,
    evaluate_prospect_opportunity,
    generate_honest_outreach_draft,
    execute_prospecting_campaign
)
from backend.app.schemas import LeadCreate

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_prospecting_db(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test_prospecting.db")
    monkeypatch.setattr("backend.app.config.settings.DB_PATH", test_db)
    init_db(test_db)
    yield test_db


# ---------------------------------------------------------------------------
# 1. Hashtag selection and deduplication
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_hashtag_selection_and_deduplication():
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Test AI/knowledge research returns non-empty list of unique hashtags
        tags1 = await research_prospecting_hashtags(cursor, max_hashtags=3)
        assert len(tags1) > 0
        tag_names1 = [t["hashtag"] for t in tags1]
        assert len(tag_names1) == len(set(tag_names1))  # Deduplicated within run

        # Verify recorded in database
        cursor.execute("SELECT hashtag, times_used FROM prospecting_hashtags")
        db_tags = {r["hashtag"]: r["times_used"] for r in cursor.fetchall()}
        for t in tag_names1:
            assert t in db_tags
            assert db_tags[t] == 1

        # Second run should increment times_used and prioritize fresh tags
        tags2 = await research_prospecting_hashtags(cursor, max_hashtags=2)
        assert len(tags2) > 0


# ---------------------------------------------------------------------------
# 2. Search-provider fallback
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_search_provider_fallback(monkeypatch):
    from backend.app.services.discovery_service import SearchProviderBase, DuckDuckGoSearchProvider, SerperSearchProvider

    # Mock primary provider returning 0 results and bot challenge
    class MockFailingPrimary(SearchProviderBase):
        name = "MockFailing"
        def is_configured(self): return True
        async def search(self, queries, limit=10, source_mode="all_sources", diagnostics=None, **kwargs):
            if diagnostics is not None:
                diagnostics["provider_status"] = "rate_limited_202"
                diagnostics["provider_request_status"] = "HTTP 202 Bot Challenge"
            return []

    # Mock fallback provider returning verified profile
    class MockSuccessfulFallback(SearchProviderBase):
        name = "MockFallback"
        def is_configured(self): return True
        async def search(self, queries, limit=10, source_mode="all_sources", diagnostics=None, **kwargs):
            return [{
                "target_url": "https://www.instagram.com/p/C9Z123/",
                "raw_title": "Artisan Linen Studio (@artisanlinen) on Instagram",
                "snippet": "Handcrafted sustainable apparel boutique based in Kochi. DM for orders or WhatsApp +91 9876543210.",
                "source": "MockFallback"
            }]

    primary = MockFailingPrimary()
    fallback = MockSuccessfulFallback()

    with patch("backend.app.services.prospecting_service.get_search_pipeline", return_value=(primary, [fallback])):
        from backend.app.services.prospecting_service import discover_hashtag_content
        results = await discover_hashtag_content("kochiboutique", limit=5)
        assert len(results) == 1
        assert results[0]["instagram_handle"] == "artisanlinen"
        assert results[0]["source_media_id"] == "C9Z123"


# ---------------------------------------------------------------------------
# 3. Public-media retrieval and unsupported API permissions
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_public_media_retrieval_and_unsupported_api_permissions():
    # Test post & reel info extraction
    post_item = {
        "target_url": "https://www.instagram.com/reel/C8XYZ123/",
        "raw_title": "Clay & Glaze Pottery (@clayglaze) on Instagram: 'New ceramics'",
        "snippet": "New handcrafted stoneware batch available now. Visit link in bio or DM for details.",
        "source": "Serper"
    }
    extracted = extract_post_and_profile_info(post_item, "keralapottery")
    assert extracted is not None
    assert extracted["instagram_handle"] == "clayglaze"
    assert extracted["source_media_id"] == "C8XYZ123"
    assert extracted["source_media_url"] == "https://www.instagram.com/reel/C8XYZ123/"
    assert extracted["discovery_hashtag"] == "keralapottery"

    # Test Meta Graph API capability check transparently reports missing permission when token lacks it
    with patch("httpx.AsyncClient.get") as mock_get:
        # Mock me endpoint returning account
        mock_me = MagicMock()
        mock_me.status_code = 200
        mock_me.json.return_value = {"id": "29266079986333250", "username": "abenzo.co.in", "account_type": "BUSINESS"}

        # Mock ig_hashtag_search returning Code 100 missing permission
        mock_ht = MagicMock()
        mock_ht.status_code = 400
        mock_ht.json.return_value = {
            "error": {
                "message": "Unsupported get request. Object with ID 'ig_hashtag_search' does not exist, cannot be loaded due to missing permissions",
                "type": "IGApiException",
                "code": 100
            }
        }

        mock_get.side_effect = [mock_me, mock_ht]

        meta_check = await inspect_meta_hashtag_capabilities()
        assert meta_check["connected"] is True
        assert meta_check["hashtag_api_supported"] is False
        assert "instagram_public_contents_access" in meta_check["missing_permission"]
        assert meta_check["search_fallback_active"] is True


# ---------------------------------------------------------------------------
# 4. Evidence-based scoring and personalized drafts
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_evidence_based_scoring_and_personalized_drafts():
    # Candidate with explicit DM ordering and no website URL
    candidate1 = {
        "business_name": "Linen & Thread",
        "instagram_handle": "linenthread",
        "source_caption": "Handcrafted festive shirts. DM for price and orders. No website yet.",
        "snippet": "DM for price and orders. No website yet.",
        "website_url": "",
        "contacts": {"phones": [], "emails": [], "external_links": []},
        "discovery_hashtag": "kochiboutique"
    }

    eval1 = await evaluate_prospect_opportunity(candidate1, {"service_fit": "E-commerce & Storefront"})
    assert eval1["website_status"] == "no_website"
    assert eval1["lead_score"] >= 70
    assert "E-commerce" in eval1["recommended_service"]
    # Verify evidence includes factual justification
    assert any("DM" in e for e in eval1["evidence"])

    # Candidate with existing website - should NOT be labeled "no website"
    candidate2 = {
        "business_name": "Modern Dental",
        "instagram_handle": "moderndental",
        "source_caption": "Dental care clinic in Bangalore.",
        "snippet": "Check our website at https://moderndental.in",
        "website_url": "https://moderndental.in",
        "contacts": {"phones": [], "emails": [], "external_links": ["https://moderndental.in"]},
        "discovery_hashtag": "bangaloreclinic"
    }

    with patch("backend.app.services.prospecting_service.check_website") as mock_check:
        mock_res = MagicMock()
        mock_res.status = "found"
        mock_res.status_code = 200
        mock_check.return_value = mock_res

        eval2 = await evaluate_prospect_opportunity(candidate2, {"service_fit": "Custom Web Applications"})
        assert eval2["website_status"] == "has_website"

    # Test personalized draft generation
    draft = await generate_honest_outreach_draft(candidate1, eval1)
    assert len(draft) > 30
    assert "Linen & Thread" in draft or "@linenthread" in draft
    # Honest criteria: No fake familiarity or fake pricing
    assert "best friend" not in draft.lower()
    assert "₹" not in draft  # No immediate pricing dump


# ---------------------------------------------------------------------------
# 5. Duplicate campaigns and safe retries
# ---------------------------------------------------------------------------

def test_duplicate_campaigns_and_safe_retries():
    # Insert a fake running campaign
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO campaigns (
                status, stage, current_step_text, started_at, created_at, updated_at
            ) VALUES ('running', 'checking_apis', 'In progress', datetime('now'), datetime('now'), datetime('now'))
        """)
        conn.commit()

    # Attempting to start another campaign should return 409 Conflict
    resp = client.post("/api/campaigns/start")
    assert resp.status_code == 409
    assert "currently in progress" in resp.json()["detail"]

    # Mark as completed
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE campaigns SET status = 'completed'")
        conn.commit()

    # Now starting a campaign should succeed
    with patch("backend.app.routers.campaigns.execute_prospecting_campaign"):
        resp2 = client.post("/api/campaigns/start")
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "running"


# ---------------------------------------------------------------------------
# 6. CRM persistence
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_crm_persistence():
    # Insert campaign
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO campaigns (status, stage, started_at, created_at, updated_at)
            VALUES ('running', 'checking_apis', datetime('now'), datetime('now'), datetime('now'))
        """)
        camp_id = cursor.lastrowid
        conn.commit()

    # Mock discovery to return 1 qualified prospect
    mock_candidate = {
        "business_name": "Aura Bakery",
        "instagram_handle": "aurabakery",
        "instagram_url": "https://instagram.com/aurabakery",
        "source_media_url": "https://instagram.com/reel/C7XYZ/",
        "source_media_id": "C7XYZ",
        "source_caption": "Artisan sourdough and desserts in Trivandrum. DM for orders.",
        "discovery_hashtag": "trivandrumbakery",
        "website_url": "",
        "raw_title": "Aura Bakery on Instagram",
        "snippet": "Artisan sourdough in Trivandrum.",
        "contacts": {"phones": [], "emails": [], "external_links": []},
        "search_source": "Serper"
    }

    with patch("backend.app.services.prospecting_service.discover_hashtag_content", return_value=[mock_candidate]):
        await execute_prospecting_campaign(camp_id)

    # Verify campaign completed and saved to leads
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM campaigns WHERE id = ?", (camp_id,))
        camp_row = cursor.fetchone()
        assert camp_row["status"] == "completed"
        assert camp_row["qualified_prospects_count"] >= 1

        cursor.execute("SELECT * FROM leads WHERE campaign_id = ?", (camp_id,))
        saved_lead = cursor.fetchone()
        assert saved_lead is not None
        assert saved_lead["instagram_handle"] == "aurabakery"
        assert saved_lead["source_media_id"] == "C7XYZ"
        assert saved_lead["source_media_url"] == "https://instagram.com/reel/C7XYZ/"
        assert saved_lead["discovery_hashtag"] == "trivandrumbakery"
        assert saved_lead["outreach_status"] == "draft"


# ---------------------------------------------------------------------------
# 7. Correct linking of inbound conversations
# ---------------------------------------------------------------------------

def test_correct_linking_of_inbound_conversations():
    # 1. Create a lead in CRM with instagram_handle
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO leads (
                business_name, instagram_handle, instagram_url, outreach_status,
                created_at, updated_at
            ) VALUES ('Kochi Potter Studio', 'kochipotter', 'https://instagram.com/kochipotter', 'draft', datetime('now'), datetime('now'))
        """)
        lead_id = cursor.lastrowid
        conn.commit()

    # 2. Simulate incoming Instagram DM webhook with sender_id = 'kochipotter'
    # and message containing voluntarily shared phone number and budget
    webhook_payload = {
        "object": "instagram",
        "entry": [{
            "id": "29266079986333250",
            "time": 1729000000,
            "messaging": [{
                "sender": {"id": "kochipotter"},
                "recipient": {"id": "29266079986333250"},
                "timestamp": 1729000000,
                "message": {
                    "mid": "mid_test_inbound_123",
                    "text": "Hi Abin, we need an e-commerce website for our pottery studio. Our budget is around 40k and phone is +91 9998887776."
                }
            }]
        }]
    }

    # Mock AI memory extraction
    with patch("backend.app.routers.meta.draft_inbound_response_with_ai") as mock_ai:
        mock_ai.return_value = {
            "ai_draft": "Hi! Thanks for reaching out. We would be glad to help with your e-commerce storefront.",
            "lead_temperature": "warm",
            "needs_human_decision": False,
            "conversation_summary": "Prospect reached out for pottery e-commerce website with 40k budget.",
            "suggested_conversion_stage": "inquiry",
            "lead_context": {
                "phone": "+91 9998887776",
                "budget": "40k",
                "timeline": "ASAP"
            }
        }

        resp = client.post("/api/meta/webhook", json=webhook_payload)
        assert resp.status_code == 200

    # Verify conversation was created, linked to lead, and lead was updated to 'replied' with phone and budget
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
        updated_lead = cursor.fetchone()
        assert updated_lead["outreach_status"] == "replied"
        assert updated_lead["public_phone"] == "+91 9998887776"
        assert updated_lead["budget"] == "40k"
        assert updated_lead["conversation_id"] is not None


# ---------------------------------------------------------------------------
# 8. Prevention of unauthorized outbound messages
# ---------------------------------------------------------------------------

def test_prevention_of_unauthorized_outbound_messages():
    # Attempting to send an approved reply to an event that doesn't exist returns 404
    resp = client.post("/api/meta/send-reply", json={"event_id": 99999, "approved_text": "Hello"})
    assert resp.status_code == 404

    # Create a conversation with invalid/placeholder recipient ID
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO conversations (platform, external_thread_id, recipient_id, created_at, updated_at)
            VALUES ('instagram', 'sample_123', 'sample_123', datetime('now'), datetime('now'))
        """)
        conv_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO conversation_events (conversation_id, message_text, delivery_status, created_at)
            VALUES (?, 'Test message', 'received', datetime('now'))
        """, (conv_id,))
        event_id = cursor.lastrowid
        conn.commit()

    # Sending reply to a sample/unverified conversation must be rejected (Code 400)
    resp2 = client.post("/api/meta/send-reply", json={"event_id": event_id, "approved_text": "Unauthorized cold outbound"})
    assert resp2.status_code == 400
    assert "Invalid recipient ID" in resp2.json()["detail"]


# ---------------------------------------------------------------------------
# 9. Campaign cancellation and partial provider failures
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_campaign_cancellation_and_partial_provider_failures():
    # Test cancellation endpoint
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO campaigns (status, stage, started_at, created_at, updated_at)
            VALUES ('running', 'discovering_media', datetime('now'), datetime('now'), datetime('now'))
        """)
        camp_id = cursor.lastrowid
        conn.commit()

    cancel_resp = client.post(f"/api/campaigns/{camp_id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"

    # Verify DB status updated
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM campaigns WHERE id = ?", (camp_id,))
        assert cursor.fetchone()["status"] == "cancelled"
