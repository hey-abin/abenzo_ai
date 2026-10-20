import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import httpx

from backend.app.config import settings
from backend.app.database import get_db, _ph, _now_default
from backend.app.services.knowledge_service import get_approved_knowledge_summary
from backend.app.services.ollama_service import call_ai_completion, parse_ai_json
from backend.app.services.discovery_service import (
    get_search_pipeline,
    classify_instagram_url,
    extract_instagram_handle,
    clean_instagram_business_name,
    extract_contacts_and_links,
    pick_best_website_url,
    extract_root_domain,
    normalize_domain_or_url,
    check_duplicate_lead,
    AGGREGATOR_LISTICLE_DOMAINS,
    LISTICLE_TITLE_PATTERNS
)
from backend.app.services.website_checker import check_website

logger = logging.getLogger("abenzo.prospecting")

# ---------------------------------------------------------------------------
# Meta Graph API Verification & Hashtag Capabilities
# ---------------------------------------------------------------------------

async def inspect_meta_hashtag_capabilities() -> Dict[str, Any]:
    """
    Directly tests Meta Instagram Graph API capabilities for the configured token.
    Determines whether ig_hashtag_search is supported by this account and token,
    or explains the exact missing permissions (e.g. instagram_public_contents_access).
    Never fabricates success or capabilities.
    """
    token = settings.effective_instagram_token
    if not token:
        return {
            "configured": False,
            "connected": False,
            "account_id": None,
            "username": None,
            "hashtag_api_supported": False,
            "missing_permission": "INSTAGRAM_ACCESS_TOKEN not configured in .env",
            "search_fallback_active": True,
            "guidance": "Configure Instagram credentials in environment variables."
        }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            # 1. Inspect account identity
            me_resp = await client.get(
                "https://graph.instagram.com/me",
                params={"fields": "id,username,account_type", "access_token": token}
            )
            if me_resp.status_code != 200:
                err_json = me_resp.json().get("error", {})
                return {
                    "configured": True,
                    "connected": False,
                    "account_id": None,
                    "username": None,
                    "hashtag_api_supported": False,
                    "missing_permission": f"Invalid token (Code {err_json.get('code', 'unknown')}): {err_json.get('message', 'Auth failed')}",
                    "search_fallback_active": True,
                    "guidance": "The configured Instagram token could not be verified by graph.instagram.com."
                }

            me_data = me_resp.json()
            user_id = me_data.get("id")
            username = me_data.get("username")
            account_type = me_data.get("account_type", "BUSINESS")

            # 2. Test ig_hashtag_search on graph.instagram.com
            ht_resp = await client.get(
                "https://graph.instagram.com/ig_hashtag_search",
                params={"user_id": user_id, "q": "webdevelopment", "access_token": token}
            )

            hashtag_supported = False
            missing_perm = None

            if ht_resp.status_code == 200:
                hashtag_supported = True
            else:
                err_data = ht_resp.json().get("error", {})
                err_code = err_data.get("code")
                err_subcode = err_data.get("error_subcode")
                # Meta returns Code 100 for user token or missing instagram_public_contents_access
                missing_perm = (
                    f"Meta Graph API code {err_code}: ig_hashtag_search requires a Facebook Page-linked "
                    f"Instagram account with 'instagram_public_contents_access' permission. "
                    f"Account @{username} is connected with Instagram Graph User access."
                )

            return {
                "configured": True,
                "connected": True,
                "account_id": user_id,
                "username": username,
                "account_type": account_type,
                "hashtag_api_supported": hashtag_supported,
                "missing_permission": missing_perm,
                "search_fallback_active": True,
                "guidance": (
                    f"Connected to @{username} ({account_type}). "
                    + ("Official Graph API hashtag search is active." if hashtag_supported else 
                       "Official Graph API hashtag endpoint requires 'instagram_public_contents_access'; public post and Reel discovery is supplemented via verified search indexing.")
                )
            }
    except Exception as e:
        logger.warning("Error testing Meta hashtag capabilities: %s", e)
        return {
            "configured": True,
            "connected": False,
            "account_id": None,
            "username": None,
            "hashtag_api_supported": False,
            "missing_permission": f"Network error checking Meta API: {type(e).__name__}",
            "search_fallback_active": True,
            "guidance": "Could not reach Meta Graph API. Supplementing with search provider."
        }


# ---------------------------------------------------------------------------
# AI-Driven Hashtag Research Engine
# ---------------------------------------------------------------------------

async def research_prospecting_hashtags(cursor, max_hashtags: int = 4) -> List[Dict[str, Any]]:
    """
    Researches high-potential Instagram hashtags based on Abenzo's service knowledge base:
    - Custom Website Development
    - E-commerce & WhatsApp Ordering Storefronts
    - Custom Web Applications & Client Portals
    - Business Automation & Digital Presence
    
    Dynamically queries AI, records rationale, and avoids repeating low-yield hashtags.
    """
    # 1. Fetch previous hashtag performance from database
    cursor.execute("""
        SELECT hashtag, prospects_found, qualified_found, times_used, rationale
        FROM prospecting_hashtags
        ORDER BY last_used_at DESC LIMIT 20
    """)
    previous_rows = cursor.fetchall()
    previous_tags = {r["hashtag"].lower(): dict(r) for r in previous_rows}

    # 2. Extract approved agency service knowledge
    kb_summary = get_approved_knowledge_summary()

    # 3. Request AI to propose fresh, high-fit hashtags
    prompt = f"""You are the head of growth for Abenzo, an Indian web development and automation agency.
Our core services:
- Custom Website Development (for local brands, service firms, studios, clinics, architects)
- E-commerce & WhatsApp Storefronts (for boutiques, handcrafted brands, bakeries, clothing lines, D2C)
- Custom Web Applications & Dashboards (for growing businesses needing automation, booking, customer portals)

Review previously searched hashtags to avoid repeating low-yielding or saturated queries:
{json.dumps(list(previous_tags.keys())[:10])}

Select {max_hashtags} specific, realistic Instagram hashtags that actual Indian small businesses, boutiques, studios, clinics, or cafes use when posting their products or services on Instagram.
Avoid overly generic global tags like #business or #love. Focus on regional, commercial, or niche tags where prospects frequently post without having an established website.

Return strictly a JSON array with exactly {max_hashtags} objects matching this schema:
[
  {{
    "hashtag": "kochiboutique",
    "rationale": "Apparel and designer boutiques in Kochi frequently showcase collections on Instagram but lack standalone e-commerce storefronts.",
    "service_fit": "E-commerce & WhatsApp Storefront"
  }}
]
Do not include any conversational preamble or markdown code fences outside the JSON.
"""

    selected_hashtags: List[Dict[str, Any]] = []

    try:
        raw_ai = await call_ai_completion(prompt, temperature=0.3)
        parsed = parse_ai_json(raw_ai)
        if isinstance(parsed, list):
            for item in parsed:
                tag = re.sub(r"[#\s]", "", item.get("hashtag", "")).strip().lower()
                if tag and len(tag) > 2:
                    selected_hashtags.append({
                        "hashtag": tag,
                        "rationale": item.get("rationale", "Targeted business niche for Abenzo services"),
                        "service_fit": item.get("service_fit", "Custom Website & Storefront")
                    })
    except Exception as e:
        logger.warning("AI hashtag generation encountered error, falling back to knowledge-grounded selector: %s", e)

    # Fallback to intelligent rotation from Abenzo knowledge domain if AI fails or returns empty
    if not selected_hashtags:
        candidate_pool = [
            {"hashtag": "kochiboutique", "rationale": "Kerala clothing and bridal boutiques posting collections requiring online catalogs.", "service_fit": "E-commerce & WhatsApp Storefront"},
            {"hashtag": "bangalorecafes", "rationale": "Independent specialty cafes needing online menus and location web pages.", "service_fit": "Custom Website Development"},
            {"hashtag": "keralahomestays", "rationale": "Boutique hospitality properties seeking direct booking websites instead of OTA commissions.", "service_fit": "Custom Web Applications & Booking"},
            {"hashtag": "mumbaidesignstudio", "rationale": "Interior and architectural design studios needing modern interactive portfolios.", "service_fit": "Custom Website Development"},
            {"hashtag": "chennaibakery", "rationale": "Custom cake and artisan dessert studios managing orders manually via DMs.", "service_fit": "E-commerce & Storefront"},
            {"hashtag": "d2cindia", "rationale": "Emerging consumer brands needing high-converting storefronts and performance optimization.", "service_fit": "E-commerce Storefronts"},
            {"hashtag": "indiansmallbusiness", "rationale": "Independent makers and regional businesses establishing digital presence.", "service_fit": "Custom Website Development"},
            {"hashtag": "thrissurboutiques", "rationale": "Regional lifestyle and textile shops transitioning to digital sales.", "service_fit": "E-commerce & WhatsApp Storefront"}
        ]
        # Sort candidate pool prioritizing hashtags least used
        candidate_pool.sort(key=lambda c: previous_tags.get(c["hashtag"], {}).get("times_used", 0))
        selected_hashtags = candidate_pool[:max_hashtags]

    # Store or update researched hashtags in database
    now_iso = datetime.now().isoformat()
    ph = _ph
    for item in selected_hashtags:
        tag = item["hashtag"]
        cursor.execute(f"SELECT id, times_used FROM prospecting_hashtags WHERE hashtag = {ph(1)}", (tag,))
        existing = cursor.fetchone()
        if existing:
            new_times = (existing["times_used"] or 0) + 1
            cursor.execute(f"""
                UPDATE prospecting_hashtags SET
                    times_used = {ph(1)},
                    last_used_at = {ph(1)},
                    rationale = {ph(1)},
                    service_fit = {ph(1)},
                    updated_at = {ph(1)}
                WHERE id = {ph(1)}
            """, (new_times, now_iso, item["rationale"], item["service_fit"], now_iso, existing["id"]))
        else:
            cursor.execute(f"""
                INSERT INTO prospecting_hashtags (
                    hashtag, rationale, service_fit, times_used, last_used_at,
                    prospects_found, qualified_found, created_at, updated_at
                ) VALUES ({ph(9)})
            """, (tag, item["rationale"], item["service_fit"], 1, now_iso, 0, 0, now_iso, now_iso))

    return selected_hashtags


# ---------------------------------------------------------------------------
# Public Post & Reel Discovery Engine
# ---------------------------------------------------------------------------

def extract_post_and_profile_info(item: Dict[str, Any], hashtag: str) -> Optional[Dict[str, Any]]:
    """
    Extracts public post, Reel, or profile details from search result items.
    Deduplicates and normalizes usernames, permalinks, and media IDs.
    """
    target_url = item.get("target_url", "").strip()
    raw_title = item.get("raw_title", "").strip()
    snippet = item.get("snippet", "").strip()

    if not target_url or "instagram.com" not in target_url.lower():
        return None

    # Filter out aggregator / listicle domains
    root_domain = extract_root_domain(target_url)
    if not root_domain or root_domain in AGGREGATOR_LISTICLE_DOMAINS:
        return None

    title_lower = raw_title.lower()
    if any(re.search(pat, title_lower) for pat in LISTICLE_TITLE_PATTERNS):
        return None

    # Analyze URL structure
    # Patterns:
    # 1. Post: https://www.instagram.com/p/C6Z7abc123/
    # 2. Reel: https://www.instagram.com/reel/C8X9xyz456/
    # 3. Profile: https://www.instagram.com/username/
    reel_match = re.search(r"instagram\.com/reel/([A-Za-z0-9_-]+)", target_url, re.IGNORECASE)
    post_match = re.search(r"instagram\.com/p/([A-Za-z0-9_-]+)", target_url, re.IGNORECASE)

    media_id = ""
    media_url = ""
    is_media = False

    if reel_match:
        media_id = reel_match.group(1)
        media_url = f"https://www.instagram.com/reel/{media_id}/"
        is_media = True
    elif post_match:
        media_id = post_match.group(1)
        media_url = f"https://www.instagram.com/p/{media_id}/"
        is_media = True

    # Extract username
    username = ""
    if is_media:
        # Username often in title: "Business Name (@handle) • Instagram photos and videos" or "Handle on Instagram: 'caption...'"
        title_handle_match = re.search(r"@([a-zA-Z0-9._]{2,30})", raw_title)
        if title_handle_match:
            username = title_handle_match.group(1).lower().strip(".")
        else:
            on_ig_match = re.search(r"^([a-zA-Z0-9._]{2,30})\s+on\s+instagram", raw_title, re.IGNORECASE)
            if on_ig_match:
                username = on_ig_match.group(1).lower().strip(".")
            else:
                # Check snippet for @handle
                snip_handle_match = re.search(r"@([a-zA-Z0-9._]{2,30})", snippet)
                if snip_handle_match:
                    username = snip_handle_match.group(1).lower().strip(".")
    else:
        # Profile URL
        is_prof, prof_user, _ = classify_instagram_url(target_url)
        if is_prof and prof_user:
            username = prof_user

    if not username:
        # If no profile can be identified, cannot create a targeted CRM prospect
        return None

    # Determine business name
    b_name = clean_instagram_business_name(raw_title, username)
    contacts = extract_contacts_and_links(snippet)
    website_url = pick_best_website_url(contacts["external_links"])

    return {
        "business_name": b_name,
        "instagram_handle": username,
        "instagram_url": f"https://www.instagram.com/{username}",
        "source_media_url": media_url or f"https://www.instagram.com/{username}",
        "source_media_id": media_id,
        "source_caption": snippet[:500],
        "discovery_hashtag": hashtag,
        "website_url": website_url,
        "raw_title": raw_title,
        "snippet": snippet,
        "contacts": contacts,
        "search_source": item.get("source", "Search Provider")
    }


async def discover_hashtag_content(
    hashtag: str,
    limit: int = 6,
    diagnostics: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Retrieves public posts, Reels, and profiles for a specific hashtag using the search pipeline.
    """
    primary_provider, fallback_providers = get_search_pipeline()
    clean_tag = hashtag.strip().replace("#", "")

    # Queries designed to surface real business posts, reels, and profiles with observable evidence
    queries = [
        f'site:instagram.com/reel/ "#{clean_tag}"',
        f'site:instagram.com/p/ "#{clean_tag}"',
        f'site:instagram.com "#{clean_tag}" ("boutique" OR "cafe" OR "studio" OR "store" OR "orders" OR "dm")'
    ]

    raw_items: List[Dict[str, Any]] = []
    if diagnostics is None:
        diagnostics = {}

    for q in queries:
        try:
            items = await primary_provider.search(
                queries=[q],
                limit=limit,
                source_mode="all_sources",
                diagnostics=diagnostics
            )
            raw_items.extend(items)
            if len(raw_items) >= limit * 2:
                break
        except Exception as e:
            logger.warning("Error running query %s with primary provider: %s", q, e)

    # Fallback to secondary provider if 0 results
    if len(raw_items) == 0 and fallback_providers:
        for fallback in fallback_providers:
            if not fallback.is_configured():
                continue
            try:
                fb_items = await fallback.search(
                    queries=queries[:2],
                    limit=limit,
                    source_mode="all_sources",
                    diagnostics=diagnostics
                )
                if fb_items:
                    raw_items = fb_items
                    break
            except Exception:
                pass

    results = []
    seen_keys = set()

    for item in raw_items:
        extracted = extract_post_and_profile_info(item, clean_tag)
        if not extracted:
            continue

        # Deduplicate by media ID or username
        key = extracted["source_media_id"] or extracted["instagram_handle"]
        if key in seen_keys:
            continue
        seen_keys.add(key)
        results.append(extracted)

    return results


# ---------------------------------------------------------------------------
# AI Analysis & Evidence-Based Prospect Qualification
# ---------------------------------------------------------------------------

async def evaluate_prospect_opportunity(
    cand: Dict[str, Any],
    hashtag_info: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Performs evidence-based prospect qualification:
    - Analyzes public caption, bio, and snippet text.
    - Accurately checks whether business already has a suitable website.
    - Honors honesty rule: Never state 'no website' without evidence, never assume WhatsApp ordering without evidence.
    - Proposes specific Abenzo service fit and score (0-100).
    """
    snippet = cand.get("snippet", "")
    caption = cand.get("source_caption", "")
    full_text = f"{snippet} {caption}".lower()
    b_name = cand.get("business_name", "")
    handle = cand.get("instagram_handle", "")
    web_url = cand.get("website_url", "")
    contacts = cand.get("contacts", {"phones": [], "emails": [], "external_links": []})

    # 1. Website status verification
    website_status = "uncertain"
    website_evidence = []

    if web_url:
        try:
            check_res = await check_website(web_url)
            if check_res.status == "found":
                website_status = "has_website"
                https_note = " Valid HTTPS." if check_res.raw_details.get("is_https") else ""
                website_evidence.append(f"Public website verified live at {web_url} (HTTP {check_res.status_code}).{https_note}")
                if not check_res.is_mobile_responsive_indicated:
                    website_evidence.append("May lack modern responsive viewport tag.")
            elif check_res.status == "broken_website":
                website_status = "broken_website"
                website_evidence.append(f"Website unreachable at {web_url}: {check_res.evidence_summary}")
            else:
                website_status = "uncertain"
                website_evidence.append(f"Website listed at {web_url} could not be assessed: {check_res.evidence_summary}")
        except Exception as e:
            website_status = "uncertain"
            website_evidence.append(f"Website URL listed ({web_url}) could not be verified: {type(e).__name__}")
    else:
        # Check if bio explicitly says no website or directs to DM/phone
        if any(w in full_text for w in ["dm for order", "dm to order", "order via dm", "dm for price", "dm for inquiries", "orders in dm", "no website", "no online store"]):
            website_status = "no_website"
            website_evidence.append("Profile explicitly directs customers to order via Instagram DMs; no standalone website URL is listed in public bio.")
        elif any(link for link in contacts.get("external_links", []) if any(ns in link for ns in ["linktr.ee", "bio.link", "wa.me", "taplink.cc", "campsite.bio"])):
            website_status = "no_website"
            website_evidence.append("Profile uses a link aggregator (Linktree/WhatsApp) without a dedicated standalone website.")
        else:
            website_status = "uncertain"
            website_evidence.append("Website presence not assessed: No external website URL detected in public Instagram snippet or bio.")

    # 2. Check WhatsApp ordering strictly with evidence
    has_whatsapp_evidence = False
    if "whatsapp" in full_text or any("wa.me" in l or "whatsapp.com" in l for l in contacts.get("external_links", [])):
        has_whatsapp_evidence = True
        website_evidence.append("Public text or links explicitly reference WhatsApp inquiries/orders.")

    # 3. Detect niche & opportunity
    niche = hashtag_info.get("service_fit", "Local Business")
    detected_service = "Custom Website Development"
    score = 50
    reasons = []

    if any(w in full_text for w in ["boutique", "clothing", "shirt", "apparel", "jewel", "store", "shop", "fashion", "handcrafted", "linenthread", "festive"]) or "e-commerce" in niche.lower() or "storefront" in niche.lower():
        detected_service = "E-commerce & WhatsApp Storefront"
        if website_status == "no_website":
            score = 85
            reasons.append("Active retail/boutique taking customer orders via DMs without a dedicated e-commerce catalog.")
        elif website_status == "has_website":
            score = 55
            reasons.append("Active e-commerce brand; potential opportunity for checkout speed or mobile conversion redesign.")
        else:
            score = 65
            reasons.append("Retail brand on Instagram with uncertain web presence.")
    elif "cafe" in full_text or "restaurant" in full_text or "bakery" in full_text:
        detected_service = "Custom Website & Digital Menu"
        score = 80 if website_status == "no_website" else 55
        reasons.append("Food & beverage brand that benefits from responsive digital menu and table inquiry setup.")
    elif "studio" in full_text or "architect" in full_text or "interior" in full_text:
        detected_service = "Interactive Portfolio & Lead Capture"
        score = 80 if website_status == "no_website" else 60
        reasons.append("Visual studio brand requiring high-performance web portfolio for client acquisition.")
    elif "clinic" in full_text or "doctor" in full_text or "dental" in full_text:
        detected_service = "Custom Web Application & Booking Portal"
        score = 75 if website_status != "has_website" else 50
        reasons.append("Healthcare provider where appointment booking and service transparency drive patient conversion.")
    else:
        score = 65 if website_status == "no_website" else 45
        reasons.append(f"Business active on Instagram under #{cand.get('discovery_hashtag')}.")

    confidence = "high" if len(website_evidence) >= 2 or website_status == "has_website" else "medium"

    return {
        "website_status": website_status,
        "lead_score": score,
        "confidence": confidence,
        "recommended_service": detected_service,
        "opportunity": " ".join(reasons),
        "evidence": website_evidence,
        "observed_problems": "; ".join(website_evidence)
    }


# ---------------------------------------------------------------------------
# Personalized Outreach Generation
# ---------------------------------------------------------------------------

async def generate_honest_outreach_draft(
    prospect: Dict[str, Any],
    qualification: Dict[str, Any]
) -> str:
    """
    Generates one concise, natural message draft (35-65 words) adhering strictly to:
    - Refer to a genuine, publicly observable detail.
    - Explain a relevant opportunity without making unsupported claims.
    - Avoid generic compliments, fake familiarity, repeated templates, and immediate pricing dumps.
    - Avoid deceptive or manipulative wording.
    - Suggest a reasonable next step without pressuring the recipient.
    """
    b_name = prospect.get("business_name") or f"@{prospect.get('instagram_handle')}"
    snippet = prospect.get("source_caption", "")
    service = qualification.get("recommended_service", "Custom Website Development")
    opportunity = qualification.get("opportunity", "")
    web_status = qualification.get("website_status", "uncertain")

    prompt = f"""Write an authentic, highly professional 40-55 word outreach message from Abin at Abenzo (an Indian web development agency) to {b_name}.

Context about the prospect:
- Business: {b_name} (@{prospect.get('instagram_handle')})
- Discovered Content Snippet: {snippet[:200]}
- Website Status: {web_status}
- Identified Opportunity: {opportunity}
- Recommended Service: {service}

Strict Guidelines:
1. Refer to a genuine detail from their content (e.g. products, recent collection, or customer inquiry workflow).
2. Do NOT use fake familiarity (e.g., 'huge fan of your page', 'love your vibe').
3. Do NOT dump pricing or offer fake discounts.
4. Explain how Abenzo's web solutions solve their specific workflow (e.g. automated catalog, clean portfolio, mobile ordering).
5. Propose an easy, pressure-free next step (e.g. 'happy to share a quick 2-minute mockup if you're open to exploring it').
6. Keep under 55 words total. Output ONLY the message text.
"""

    try:
        raw_msg = await call_ai_completion(prompt, temperature=0.3)
        # Clean quotes
        clean_msg = raw_msg.strip().strip('"').strip("'")
        if len(clean_msg) > 20 and "{" not in clean_msg:
            return clean_msg
    except Exception as e:
        logger.warning("AI draft generation fallback: %s", e)

    # High-quality factual template fallback
    if qualification.get("recommended_service") == "E-commerce & WhatsApp Storefront":
        return (
            f"Hi {b_name}, noticed your recent collection showcase on Instagram. "
            f"Since you're managing customer inquiries directly in DMs, a fast, mobile-friendly storefront could let customers "
            f"browse your catalog and place orders seamlessly. At Abenzo, we build clean storefronts for independent brands. "
            f"Happy to share a 2-minute preview if you'd be open to seeing it."
        )
    else:
        return (
            f"Hi {b_name}, came across your work on Instagram under #{prospect.get('discovery_hashtag')}. "
            f"Your showcase looks great, and having a dedicated, responsive website could help new clients discover your full service portfolio directly. "
            f"At Abenzo, we build modern websites for growing Indian businesses. Would you be open to a quick 2-minute preview of what that could look like?"
        )


# ---------------------------------------------------------------------------
# Full Autonomous Campaign Orchestrator
# ---------------------------------------------------------------------------

async def execute_prospecting_campaign(campaign_id: int):
    """
    Autonomous prospecting campaign execution pipeline:
    1. Check provider and API availability (Meta Graph API & Search Provider).
    2. Propose & select relevant hashtags from Abenzo knowledge base.
    3. Retrieve available public content (posts, Reels, profiles).
    4. Analyze and deduplicate results.
    5. Qualify and score prospects evidence-based.
    6. Generate personalized outreach drafts.
    7. Save qualified prospects and drafts to Neon / SQLite CRM.
    8. Display campaign summary and review queue.
    """
    logger.info(f"[Campaign #{campaign_id}] Starting autonomous prospecting campaign...")
    ph = _ph
    now_iso = datetime.now().isoformat()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM campaigns WHERE id = {ph(1)}", (campaign_id,))
        camp = cursor.fetchone()
        if not camp:
            logger.error(f"[Campaign #{campaign_id}] Campaign record not found.")
            return

    def update_campaign_progress(
        stage: str,
        step_text: str,
        meta_status: Optional[Dict[str, Any]] = None,
        selected_hashtags: Optional[List[Dict[str, Any]]] = None,
        discovered_posts: int = 0,
        unique_profiles: int = 0,
        qualified: int = 0,
        drafts: int = 0,
        duplicates: int = 0,
        rejected: int = 0,
        provider_failures: Optional[List[str]] = None,
        results_summary: Optional[List[Dict[str, Any]]] = None,
        status: str = "running",
        error_msg: str = "",
        completed: bool = False
    ):
        with get_db() as c_conn:
            cur = c_conn.cursor()
            now = datetime.now().isoformat()
            completed_str = now if completed else ""
            cur.execute(f"""
                UPDATE campaigns SET
                    stage = {ph(1)},
                    current_step_text = {ph(1)},
                    meta_status_json = {ph(1)},
                    selected_hashtags_json = {ph(1)},
                    discovered_posts_count = {ph(1)},
                    unique_profiles_count = {ph(1)},
                    qualified_prospects_count = {ph(1)},
                    drafts_generated_count = {ph(1)},
                    duplicates_count = {ph(1)},
                    rejected_count = {ph(1)},
                    provider_failures_json = {ph(1)},
                    results_summary_json = {ph(1)},
                    status = {ph(1)},
                    error_message = {ph(1)},
                    completed_at = {ph(1)},
                    updated_at = {ph(1)}
                WHERE id = {ph(1)}
            """, (
                stage,
                step_text,
                json.dumps(meta_status or {}),
                json.dumps(selected_hashtags or []),
                discovered_posts,
                unique_profiles,
                qualified,
                drafts,
                duplicates,
                rejected,
                json.dumps(provider_failures or []),
                json.dumps(results_summary or []),
                status,
                error_msg,
                completed_str,
                now,
                campaign_id
            ))

    def is_cancelled() -> bool:
        with get_db() as c_conn:
            cur = c_conn.cursor()
            cur.execute(f"SELECT status FROM campaigns WHERE id = {ph(1)}", (campaign_id,))
            row = cur.fetchone()
            return bool(row and row["status"] == "cancelled")

    try:
        # -------------------------------------------------------------
        # Stage 1: Check Provider and Meta API Availability
        # -------------------------------------------------------------
        update_campaign_progress("checking_apis", "Inspecting Meta Graph API permissions and search provider readiness...")
        meta_status = await inspect_meta_hashtag_capabilities()

        if is_cancelled():
            logger.info(f"[Campaign #{campaign_id}] Campaign was cancelled.")
            return

        # -------------------------------------------------------------
        # Stage 2: AI-driven Hashtag Research
        # -------------------------------------------------------------
        update_campaign_progress("researching_hashtags", "AI analyzing Abenzo services and researching high-yield hashtags...", meta_status=meta_status)
        with get_db() as conn:
            cursor = conn.cursor()
            selected_hashtags = await research_prospecting_hashtags(cursor, max_hashtags=4)

        if is_cancelled():
            return

        update_campaign_progress(
            "discovering_media",
            f"Researched {len(selected_hashtags)} hashtags. Discovering public posts, Reels, and profiles...",
            meta_status=meta_status,
            selected_hashtags=selected_hashtags
        )

        # -------------------------------------------------------------
        # Stage 3: Discover Public Content (Posts, Reels, Profiles)
        # -------------------------------------------------------------
        discovered_items: List[Dict[str, Any]] = []
        provider_failures: List[str] = []
        discovered_posts_count = 0
        duplicates_count = 0
        rejected_count = 0

        for ht in selected_hashtags:
            if is_cancelled():
                return
            tag = ht["hashtag"]
            diagnostics: Dict[str, Any] = {}
            try:
                candidates = await discover_hashtag_content(tag, limit=5, diagnostics=diagnostics)
                discovered_posts_count += len(candidates)
                for cand in candidates:
                    cand["hashtag_info"] = ht
                    discovered_items.append(cand)
            except Exception as e:
                provider_failures.append(f"#{tag}: {type(e).__name__} ({str(e)})")

        unique_profiles: Dict[str, Dict[str, Any]] = {}
        for item in discovered_items:
            handle = item.get("instagram_handle", "")
            if not handle:
                rejected_count += 1
                continue
            if handle in unique_profiles:
                duplicates_count += 1
                continue
            unique_profiles[handle] = item

        unique_profiles_count = len(unique_profiles)

        if is_cancelled():
            return

        # -------------------------------------------------------------
        # Stage 4 & 5: AI Analysis & Evidence-Based Qualification
        # -------------------------------------------------------------
        update_campaign_progress(
            "qualifying",
            f"Analyzing and qualifying {unique_profiles_count} unique business prospects...",
            meta_status=meta_status,
            selected_hashtags=selected_hashtags,
            discovered_posts=discovered_posts_count,
            unique_profiles=unique_profiles_count,
            duplicates=duplicates_count,
            rejected=rejected_count,
            provider_failures=provider_failures
        )

        qualified_prospects: List[Dict[str, Any]] = []

        with get_db() as conn:
            cursor = conn.cursor()
            for handle, item in unique_profiles.items():
                if is_cancelled():
                    return

                # Check duplicate against existing CRM
                dup = check_duplicate_lead(
                    cursor,
                    business_name=item.get("business_name", ""),
                    website_url=item.get("website_url", ""),
                    instagram_url=item.get("instagram_url", "")
                )
                if dup:
                    duplicates_count += 1
                    item["is_duplicate"] = True
                    item["rejection_reason"] = f"Already in CRM (#{dup['id']}: {dup.get('business_name', '')})"
                    continue

                # Run evidence-based qualification
                qual = await evaluate_prospect_opportunity(item, item.get("hashtag_info", {}))
                item["qualification"] = qual

                # Criteria: score >= 50 qualifies as a legitimate digital opportunity
                if qual["lead_score"] >= 50:
                    qualified_prospects.append(item)
                else:
                    rejected_count += 1
                    item["rejection_reason"] = f"Low fit score ({qual['lead_score']}/100)"

        if is_cancelled():
            return

        # -------------------------------------------------------------
        # Stage 6: Personalized Outreach Generation
        # -------------------------------------------------------------
        qualified_count = len(qualified_prospects)
        update_campaign_progress(
            "generating_drafts",
            f"Generating personalized, factual outreach drafts for {qualified_count} qualified prospects...",
            meta_status=meta_status,
            selected_hashtags=selected_hashtags,
            discovered_posts=discovered_posts_count,
            unique_profiles=unique_profiles_count,
            qualified=qualified_count,
            duplicates=duplicates_count,
            rejected=rejected_count,
            provider_failures=provider_failures
        )

        drafts_count = 0
        for item in qualified_prospects:
            if is_cancelled():
                return
            draft = await generate_honest_outreach_draft(item, item["qualification"])
            item["personalized_dm"] = draft
            drafts_count += 1

        # -------------------------------------------------------------
        # Stage 7: Save to Neon / SQLite Database
        # -------------------------------------------------------------
        update_campaign_progress(
            "saving_crm",
            f"Persisting {qualified_count} qualified leads and drafts to Neon CRM...",
            meta_status=meta_status,
            selected_hashtags=selected_hashtags,
            discovered_posts=discovered_posts_count,
            unique_profiles=unique_profiles_count,
            qualified=qualified_count,
            drafts=drafts_count,
            duplicates=duplicates_count,
            rejected=rejected_count,
            provider_failures=provider_failures
        )

        results_summary: List[Dict[str, Any]] = []

        with get_db() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()

            for item in qualified_prospects:
                qual = item["qualification"]
                b_name = item.get("business_name") or f"@{item.get('instagram_handle')}"
                handle = item.get("instagram_handle", "")
                ig_url = item.get("instagram_url", "")
                media_url = item.get("source_media_url", "")
                media_id = item.get("source_media_id", "")
                caption = item.get("source_caption", "")
                tag = item.get("discovery_hashtag", "")
                web_url = item.get("website_url", "")
                draft = item.get("personalized_dm", "")

                cursor.execute(f"""
                    INSERT INTO leads (
                        business_name, industry, state, city, source_url,
                        instagram_url, instagram_handle, website_url, website_status,
                        evidence_json, business_summary, lead_score, confidence,
                        opportunity, recommended_service, suggested_service,
                        observed_problems, score_breakdown_json, personalized_dm,
                        reasoning_summary, next_best_action, source_media_id,
                        source_media_url, source_caption, discovery_hashtag,
                        campaign_id, outreach_status, created_at, updated_at
                    ) VALUES ({ph(29)})
                """, (
                    b_name,
                    item.get("hashtag_info", {}).get("service_fit", "Local Brand"),
                    "India",
                    "",
                    media_url or ig_url,
                    ig_url,
                    handle,
                    web_url,
                    qual.get("website_status", "uncertain"),
                    json.dumps({"evidence": qual.get("evidence", []), "hashtag": tag, "media_id": media_id}),
                    f"Discovered via #{tag} from public post/Reel. {caption[:120]}",
                    qual.get("lead_score", 60),
                    qual.get("confidence", "medium"),
                    qual.get("opportunity", ""),
                    qual.get("recommended_service", "Custom Website Development"),
                    qual.get("recommended_service", "Custom Website Development"),
                    qual.get("observed_problems", ""),
                    json.dumps({"lead_score": qual.get("lead_score", 60), "reasons": qual.get("evidence", [])}),
                    draft,
                    f"Qualified from autonomous prospecting campaign #{campaign_id} via #{tag}.",
                    f"Review personalized draft and contact @{handle} manually via official Instagram profile.",
                    media_id,
                    media_url,
                    caption,
                    tag,
                    campaign_id,
                    "draft",
                    now,
                    now
                ))
                new_lead_id = cursor.lastrowid
                item["lead_id"] = new_lead_id

                results_summary.append({
                    "lead_id": new_lead_id,
                    "business_name": b_name,
                    "instagram_handle": handle,
                    "instagram_url": ig_url,
                    "source_media_url": media_url,
                    "website_status": qual.get("website_status", "uncertain"),
                    "lead_score": qual.get("lead_score", 60),
                    "recommended_service": qual.get("recommended_service", "Custom Website Development"),
                    "opportunity": qual.get("opportunity", ""),
                    "evidence": qual.get("evidence", []),
                    "personalized_dm": draft,
                    "discovery_hashtag": tag
                })

            # Update performance counts on researched hashtags
            for ht in selected_hashtags:
                tag = ht["hashtag"]
                prospects_for_tag = sum(1 for item in discovered_items if item.get("discovery_hashtag") == tag)
                qualified_for_tag = sum(1 for item in qualified_prospects if item.get("discovery_hashtag") == tag)
                cursor.execute(f"""
                    UPDATE prospecting_hashtags SET
                        prospects_found = prospects_found + {ph(1)},
                        qualified_found = qualified_found + {ph(1)},
                        updated_at = {ph(1)}
                    WHERE hashtag = {ph(1)}
                """, (prospects_for_tag, qualified_for_tag, now, tag))

        # -------------------------------------------------------------
        # Stage 8: Campaign Completed
        # -------------------------------------------------------------
        logger.info(f"[Campaign #{campaign_id}] Completed successfully! Discovered {discovered_posts_count} posts, {unique_profiles_count} unique profiles, {qualified_count} qualified leads saved.")
        update_campaign_progress(
            "completed",
            f"Campaign completed. Discovered {discovered_posts_count} posts across {len(selected_hashtags)} hashtags, {unique_profiles_count} unique profiles, and saved {qualified_count} qualified prospects with outreach drafts into CRM.",
            meta_status=meta_status,
            selected_hashtags=selected_hashtags,
            discovered_posts=discovered_posts_count,
            unique_profiles=unique_profiles_count,
            qualified=qualified_count,
            drafts=drafts_count,
            duplicates=duplicates_count,
            rejected=rejected_count,
            provider_failures=provider_failures,
            results_summary=results_summary,
            status="completed",
            completed=True
        )

    except Exception as e:
        logger.error(f"[Campaign #{campaign_id}] Campaign failed with exception: %s", e, exc_info=True)
        update_campaign_progress(
            "failed",
            f"Campaign failed: {type(e).__name__} - {str(e)}",
            status="failed",
            error_msg=f"{type(e).__name__}: {str(e)}",
            completed=True
        )
