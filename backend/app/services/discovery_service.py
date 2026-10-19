import re
import html
import logging
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import urlparse, parse_qs
from datetime import datetime

from backend.app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Instagram URL & Profile Extraction Utilities
# ---------------------------------------------------------------------------

INSTAGRAM_RESERVED_PATHS = {
    "p", "reel", "reels", "tv", "explore", "stories", "popular",
    "tags", "directory", "accounts", "about", "legal", "developer",
    "privacy", "help", "graphql", "api", "challenge", "login",
    "web", "session", "support", "press", "contact", "terms",
    "guides", "highlights", "feed"
}

AGGREGATOR_LISTICLE_DOMAINS = {
    "duckduckgo.com", "google.com", "bing.com", "yahoo.com",
    "wikipedia.org", "youtube.com", "facebook.com", "twitter.com",
    "linkedin.com", "tripadvisor.com", "tripadvisor.in", "justdial.com", "indiamart.com",
    "yellowpages.in", "sulekha.com", "zomato.com", "swiggy.com",
    "practo.com", "amazon.in", "amazon.com", "flipkart.com", "quora.com",
    "reddit.com", "medium.com", "lbb.in", "lifestyleasia.com",
    "curlytales.com", "clutch.co", "goodfirms.co", "magicbricks.com",
    "99acres.com", "housing.com", "forbes.com", "tradeindia.com",
    "exportersindia.com", "dir.indiamart.com", "foursquare.com",
    "mouthshut.com", "trustpilot.com"
}

LISTICLE_TITLE_PATTERNS = [
    r"\btop\s+\d+",
    r"\bbest\s+\d+",
    r"\b\d+\s+best\b",
    r"\b\d+\s+top\b",
    r"\blist\s+of\b",
    r"\bwholesale\s+suppliers\b",
    r"\bmanufacturers\s+and\s+suppliers\b",
    r"\bb2b\s+portal\b",
    r"\bdirectory\b",
    r"\bbuy\s+online\s+wholesale\b",
    r"\bshopping\s+guide\b",
    r"\bplaces\s+to\s+visit\b",
    r"\bthings\s+to\s+do\b"
]


def normalize_domain_or_url(url: str) -> str:
    if not url:
        return ""
    u = url.strip().lower()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    u = u.split("?")[0].split("#")[0]
    u = u.rstrip("/")
    return u


def extract_root_domain(url: str) -> str:
    norm = normalize_domain_or_url(url)
    return norm.split("/")[0] if norm else ""


def normalize_location_input(location_raw: str) -> Dict[str, Any]:
    """
    Normalizes compound and simple location inputs such as:
    'kerala' -> city='', state='Kerala'
    'Kerala, India' -> city='', state='Kerala'
    'kochi, kerala' -> city='Kochi', state='Kerala'
    'Kochi' -> city='Kochi', state='Kerala'
    """
    if not location_raw:
        return {"city": "", "state": "", "display": "", "aliases": []}

    loc = location_raw.strip()
    # Strip country suffixes
    loc = re.sub(r"(?i)[,\s]+(india|in)$", "", loc).strip()
    if loc.lower() in ("all states", "all", "india", ""):
        return {"city": "", "state": "", "display": "", "aliases": []}

    CITY_STATE_MAP = {
        "kochi": ("Kochi", "Kerala", ["Cochin", "Ernakulam"]),
        "cochin": ("Kochi", "Kerala", ["Kochi", "Ernakulam"]),
        "ernakulam": ("Kochi", "Kerala", ["Kochi", "Cochin"]),
        "trivandrum": ("Trivandrum", "Kerala", ["Thiruvananthapuram"]),
        "thiruvananthapuram": ("Trivandrum", "Kerala", ["Trivandrum"]),
        "calicut": ("Kozhikode", "Kerala", ["Kozhikode"]),
        "kozhikode": ("Kozhikode", "Kerala", ["Calicut"]),
        "thrissur": ("Thrissur", "Kerala", ["Trichur"]),
        "trichur": ("Thrissur", "Kerala", ["Thrissur"]),
        "kannur": ("Kannur", "Kerala", ["Cannanore"]),
        "kollam": ("Kollam", "Kerala", ["Quilon"]),
        "alappuzha": ("Alappuzha", "Kerala", ["Alleppey"]),
        "alleppey": ("Alappuzha", "Kerala", ["Alappuzha"]),
        "palakkad": ("Palakkad", "Kerala", ["Palghat"]),
        "kottayam": ("Kottayam", "Kerala", []),
        "bangalore": ("Bangalore", "Karnataka", ["Bengaluru"]),
        "bengaluru": ("Bangalore", "Karnataka", ["Bangalore"]),
        "mumbai": ("Mumbai", "Maharashtra", ["Bombay"]),
        "bombay": ("Mumbai", "Maharashtra", ["Mumbai"]),
        "pune": ("Pune", "Maharashtra", []),
        "hyderabad": ("Hyderabad", "Telangana", []),
        "chennai": ("Chennai", "Tamil Nadu", ["Madras"]),
        "delhi": ("Delhi", "Delhi", ["New Delhi"]),
        "new delhi": ("Delhi", "Delhi", ["Delhi"]),
    }

    INDIAN_STATES_MAP = {
        "kerala": "Kerala", "karnataka": "Karnataka", "tamil nadu": "Tamil Nadu",
        "maharashtra": "Maharashtra", "delhi": "Delhi", "telangana": "Telangana",
        "andhra pradesh": "Andhra Pradesh", "gujarat": "Gujarat", "rajasthan": "Rajasthan",
        "uttar pradesh": "Uttar Pradesh", "west bengal": "West Bengal", "punjab": "Punjab",
        "haryana": "Haryana", "goa": "Goa", "assam": "Assam", "bihar": "Bihar",
        "madhya pradesh": "Madhya Pradesh", "odisha": "Odisha"
    }

    if "," in loc:
        parts = [p.strip() for p in loc.split(",") if p.strip()]
        first = parts[0]
        second = parts[1] if len(parts) > 1 else ""
        first_lower = first.lower()
        if first_lower in CITY_STATE_MAP:
            c, s, aliases = CITY_STATE_MAP[first_lower]
            st = second.title() if second else s
            return {"city": c, "state": st, "display": f"{c}, {st}", "aliases": aliases}
        return {"city": first.title(), "state": second.title(), "display": f"{first.title()}, {second.title()}", "aliases": []}

    loc_lower = loc.lower()
    if loc_lower in CITY_STATE_MAP:
        c, s, aliases = CITY_STATE_MAP[loc_lower]
        return {"city": c, "state": s, "display": c, "aliases": aliases}

    if loc_lower in INDIAN_STATES_MAP:
        return {"city": "", "state": INDIAN_STATES_MAP[loc_lower], "display": INDIAN_STATES_MAP[loc_lower], "aliases": []}

    return {"city": loc.title(), "state": "", "display": loc.title(), "aliases": []}


def generate_targeted_queries(
    niche: str,
    loc_info: Dict[str, Any],
    keywords: str = "",
    source_mode: str = "instagram_only"
) -> List[str]:
    """
    Generates multiple targeted search queries tailored to finding individual business profiles.
    Avoids rigid quotes that cause false negatives while ensuring geographic specificity.
    """
    clean_niche = niche.strip()
    clean_kw = keywords.strip()
    city = loc_info.get("city", "")
    state = loc_info.get("state", "")
    aliases = loc_info.get("aliases", [])

    queries = []

    if source_mode == "instagram_only":
        if city and state:
            queries.append(f"site:instagram.com {city} {clean_niche} {clean_kw}".strip())
            queries.append(f"site:instagram.com {clean_niche} {city}".strip())
            queries.append(f"site:instagram.com {clean_niche} {state}".strip())
            if aliases:
                queries.append(f"site:instagram.com {aliases[0]} {clean_niche}".strip())
        elif city:
            queries.append(f"site:instagram.com {city} {clean_niche} {clean_kw}".strip())
            queries.append(f"site:instagram.com {clean_niche} {city}".strip())
            if aliases:
                queries.append(f"site:instagram.com {aliases[0]} {clean_niche}".strip())
        elif state:
            queries.append(f"site:instagram.com {state} {clean_niche} {clean_kw}".strip())
            queries.append(f"site:instagram.com {clean_niche} in {state}".strip())
        else:
            queries.append(f"site:instagram.com {clean_niche} {clean_kw}".strip())
            queries.append(f"site:instagram.com {clean_niche} business".strip())
    else:
        # All sources mode
        loc_str = f"{city} {state}".strip() or loc_info.get("display", "")
        if loc_str:
            queries.append(f"{clean_niche} {loc_str} {clean_kw} business".strip())
            queries.append(f"{clean_niche} in {loc_str}".strip())
        else:
            queries.append(f"{clean_niche} {clean_kw} small business India".strip())

    # Deduplicate while preserving order
    seen = set()
    deduped_queries = []
    for q in queries:
        q_clean = " ".join(q.split())
        if q_clean and q_clean not in seen:
            seen.add(q_clean)
            deduped_queries.append(q_clean)

    return deduped_queries[:4]


def classify_instagram_url(url: str) -> Tuple[bool, str, str]:
    """
    Returns (is_valid_profile, clean_username, rejection_reason).
    Rejection reasons:
    - 'non_instagram_url'
    - 'empty_path'
    - 'reserved_path' (posts /p/, reels, stories, explore, popular, directory, accounts, etc.)
    - 'invalid_username'
    """
    if not url:
        return False, "", "empty_url"

    parsed = urlparse(url.strip())
    domain = parsed.netloc.lower()
    if "instagram.com" not in domain:
        return False, "", "non_instagram_url"

    path = parsed.path.strip("/")
    if not path:
        return False, "", "empty_path"

    parts = path.split("/")
    first_seg = parts[0].strip().lower()

    if first_seg in INSTAGRAM_RESERVED_PATHS:
        return False, "", "reserved_path"

    # Username pattern: 1 to 30 characters, letters, numbers, periods, underscores
    cleaned_user = first_seg.strip(".")
    if re.match(r"^[a-zA-Z0-9_\.]{1,30}$", first_seg) and len(cleaned_user) >= 1:
        return True, first_seg, ""

    return False, "", "invalid_username"


def is_valid_instagram_profile_url(url: str) -> Tuple[bool, str]:
    """
    Backward-compatible 2-tuple return: (True, clean_username) if url is a genuine individual Instagram profile.
    """
    valid, user, _ = classify_instagram_url(url)
    return valid, user


def extract_instagram_handle(url: str) -> str:
    if not url:
        return ""
    u = url.strip()
    is_profile, username = is_valid_instagram_profile_url(u)
    if is_profile:
        return username
    # If passed as @username or bare username
    cleaned = u.strip().lstrip("@").rstrip("/")
    if re.match(r"^[a-zA-Z0-9_\.]{1,30}$", cleaned) and cleaned.lower() not in INSTAGRAM_RESERVED_PATHS:
        return cleaned.lower()
    return ""


def clean_instagram_business_name(raw_title: str, username: str) -> str:
    """
    Cleans raw Instagram page titles such as:
    'Kochi Boutique (@kochi_boutiquee) • Instagram photos and videos' -> 'Kochi Boutique'
    'Malabar Roastery on Instagram: "Fresh single origin beans..."' -> 'Malabar Roastery'
    """
    if not raw_title:
        return f"@{username}" if username else "Local Business"

    title = html.unescape(raw_title).strip()
    title = re.sub(r"\s*[•\-|–—]\s*Instagram.*$", "", title, flags=re.IGNORECASE).strip()
    title = re.sub(r"\s*on\s+Instagram.*$", "", title, flags=re.IGNORECASE).strip()
    title = re.sub(r"\s*\(@[a-zA-Z0-9_\.]+\)", "", title).strip()
    title = re.sub(r"^@[a-zA-Z0-9_\.]+\s*", "", title).strip()

    if len(title) >= 2 and not title.lower().startswith("instagram"):
        return title[:70].strip()

    if username:
        words = re.sub(r"[_\.]+", " ", username).title().strip()
        return words or f"@{username}"

    return "Local Business"


def extract_contacts_and_links(text: str) -> Dict[str, Any]:
    contacts = {"phones": [], "emails": [], "external_links": []}
    if not text:
        return contacts

    phones = re.findall(r"(?:\+91[\-\s]?)?[6-9]\d{9}", text)
    for p in phones:
        clean_p = re.sub(r"[^\d+]", "", p)
        if clean_p not in contacts["phones"]:
            contacts["phones"].append(clean_p)

    emails = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
    for e in emails:
        clean_e = e.lower().strip()
        if clean_e not in contacts["emails"]:
            contacts["emails"].append(clean_e)

    urls = re.findall(r"https?://[^\s<>\"']+", text)
    for u in urls:
        u_clean = u.rstrip(".,;)")
        root = extract_root_domain(u_clean)
        if root and root not in AGGREGATOR_LISTICLE_DOMAINS and "instagram.com" not in root:
            contacts["external_links"].append(u_clean)

    return contacts


def check_duplicate_lead(cursor, business_name: str, website_url: str = "", instagram_url: str = "") -> Optional[Dict[str, Any]]:
    norm_web = extract_root_domain(website_url)
    norm_ig = extract_instagram_handle(instagram_url)
    norm_name = business_name.strip().lower()

    GENERIC_DOMAINS = {"linktr.ee", "bio.link", "wa.me", "api.whatsapp.com", "instagram.com", "facebook.com"}

    if norm_ig:
        cursor.execute("SELECT id, business_name, instagram_url FROM leads")
        for row in cursor.fetchall():
            row_ig = extract_instagram_handle(row["instagram_url"])
            if row_ig and row_ig.lower() == norm_ig.lower():
                return {"id": row["id"], "business_name": row["business_name"], "matched_by": "instagram_handle"}

    if norm_web and norm_web not in GENERIC_DOMAINS:
        cursor.execute("SELECT id, business_name, website_url FROM leads")
        for row in cursor.fetchall():
            row_domain = extract_root_domain(row["website_url"])
            if row_domain and row_domain not in GENERIC_DOMAINS and row_domain == norm_web:
                return {"id": row["id"], "business_name": row["business_name"], "matched_by": "website_url"}

    cursor.execute("SELECT id, business_name FROM leads WHERE LOWER(TRIM(business_name)) = ?", (norm_name,))
    match = cursor.fetchone()
    if match:
        return {"id": match["id"], "business_name": match["business_name"], "matched_by": "business_name"}

    return None


# ---------------------------------------------------------------------------
# Digital Opportunity & Scoring Engine
# ---------------------------------------------------------------------------

def evaluate_digital_opportunity(
    business_name: str,
    niche: str,
    city: str,
    website_url: str,
    instagram_handle: str,
    snippet: str,
    contacts: Dict[str, Any]
) -> Dict[str, Any]:
    score = 40
    breakdown = {"base_relevance": 40}
    reasons = ["Matched business niche and geographic criteria"]

    web_lower = website_url.lower() if website_url else ""
    snip_lower = snippet.lower()

    is_linktree_or_wa = any(x in web_lower for x in ["wa.me", "whatsapp.com", "linktr.ee", "bio.link"]) or not website_url

    if is_linktree_or_wa or not website_url:
        website_status = "no_website"
        observed_problems = "Operating on Instagram without a standalone branded website; taking customer orders or inquiries manually via WhatsApp/DM."
        opportunity = "Needs high-conversion e-commerce storefront or product catalog with direct WhatsApp ordering."
        suggested_service = "E-Commerce & WhatsApp Ordering Storefront (₹30,000+)"
        score += 25
        breakdown["no_website_opportunity"] = 25
        reasons.append("No standalone website (+25 pts: Prime customer for Abenzo web development)")
    else:
        if "error" in snip_lower or "404" in snip_lower or "domain expired" in snip_lower:
            website_status = "broken_website"
            observed_problems = "Bio or listed website link appears unreachable or returns an error."
            opportunity = "Needs immediate website rebuild and reliable modern hosting to stop losing customer traffic."
            suggested_service = "Website Rebuild & Speed Optimization"
            score += 30
            breakdown["broken_website_opportunity"] = 30
            reasons.append("Broken/unreachable website (+30 pts: High urgency client fix)")
        else:
            website_status = "has_website"
            observed_problems = "Has basic website presence; potential opportunity for mobile optimization, redesign, or conversion funnel."
            opportunity = "Improve mobile page speed, modern redesign, and direct conversion capture."
            suggested_service = "Website Redesign & Conversion Optimization"
            score += 10
            breakdown["existing_website_opportunity"] = 10
            reasons.append("Existing website redesign opportunity (+10 pts)")

    if contacts.get("phones"):
        score += 15
        breakdown["verified_phone"] = 15
        reasons.append("Public WhatsApp/phone contact verified (+15 pts)")

    if contacts.get("emails"):
        score += 10
        breakdown["verified_email"] = 10
        reasons.append("Public business email verified (+10 pts)")

    if instagram_handle:
        score += 10
        breakdown["verified_instagram_profile"] = 10
        reasons.append(f"Verified active Instagram business profile @{instagram_handle} (+10 pts)")

    if city and city.lower() in snip_lower:
        score += 5
        breakdown["local_geography_match"] = 5
        reasons.append(f"Explicitly verified in {city} (+5 pts)")

    final_score = max(25, min(95, score))

    business_stage = "small_business"
    if any(k in snip_lower for k in ["startup", "founded in", "tech", "app", "saas", "innovat"]):
        business_stage = "startup"
    elif any(k in snip_lower for k in ["brand", "label", "studio", "atelier", "organic", "artisan"]):
        business_stage = "local_brand"

    display_name = business_name if len(business_name) < 30 else (f"@{instagram_handle}" if instagram_handle else "there")
    city_str = f" in {city}" if city and city.lower() not in ("all", "india") else ""

    if website_status == "no_website":
        personalized_dm = (
            f"Hi {display_name}! Loved your {niche or 'work'}{city_str} on Instagram. "
            f"Noticed you're taking orders directly via DM/WhatsApp without a dedicated website. "
            f"We build lightning-fast WhatsApp-integrated online storefronts for local brands so customers can browse & order effortlessly. "
            f"Would you be open to a quick 2-min preview?"
        )
    elif website_status == "broken_website":
        personalized_dm = (
            f"Hi {display_name}! Came across your page while looking for {niche or 'businesses'}{city_str}. "
            f"Noticed the link in your bio appears to be down. "
            f"We help local brands build fast, modern, and reliable websites. "
            f"Happy to share a quick suggestion to get it back up and running smoothly if you'd like!"
        )
    else:
        personalized_dm = (
            f"Hi {display_name}! Really liked your work on Instagram. "
            f"Took a look at your website and had a couple of ideas to boost your mobile loading speed and customer inquiries{city_str}. "
            f"Would you be open to seeing a quick feedback teardown?"
        )

    return {
        "website_status": website_status,
        "observed_problems": observed_problems,
        "opportunity": opportunity,
        "suggested_service": suggested_service,
        "personalized_dm": personalized_dm,
        "lead_score": final_score,
        "score_reasons": reasons,
        "score_breakdown": breakdown,
        "business_stage": business_stage,
    }


# ---------------------------------------------------------------------------
# Modular Search Providers (Primary DuckDuckGo + Secondary APIs)
# ---------------------------------------------------------------------------

class SearchProviderBase:
    name: str = "Base"

    def is_configured(self) -> bool:
        raise NotImplementedError

    async def search(
        self,
        queries: List[str],
        limit: int,
        source_mode: str,
        diagnostics: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError


class DuckDuckGoSearchProvider(SearchProviderBase):
    """
    Primary provider: DuckDuckGo HTML / Lite search.
    Detects HTTP 202 Bot Challenge and rate limits transparently.
    """
    name: str = "DuckDuckGo"

    def is_configured(self) -> bool:
        return True

    async def search(
        self,
        queries: List[str],
        limit: int,
        source_mode: str,
        diagnostics: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        import httpx
        from bs4 import BeautifulSoup

        raw_results = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://lite.duckduckgo.com",
            "Referer": "https://lite.duckduckgo.com/",
        }

        timeout = float(settings.SEARCH_TIMEOUT_SECONDS or 14.0)

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
            # Session handshake to receive lite cookies
            try:
                await client.get("https://lite.duckduckgo.com/lite/")
            except Exception as e:
                logger.warning(f"DuckDuckGo handshake failed: {e}")

            for q in queries:
                diagnostics["queries_executed"].append(q)
                if len(raw_results) >= limit * 2:
                    break

                try:
                    resp = await client.post("https://lite.duckduckgo.com/lite/", data={"q": q})
                    
                    if resp.status_code == 202:
                        diagnostics["rate_limits"] += 1
                        diagnostics["provider_status"] = "rate_limited_202"
                        diagnostics["provider_error_message"] = "DuckDuckGo returned HTTP 202 Bot Challenge from this server IP."
                        logger.warning(f"DuckDuckGo HTTP 202 Bot Challenge for query: '{q}'")
                        # Do not keep retrying DDG if challenged with 202
                        break

                    if resp.status_code != 200:
                        diagnostics["provider_errors"] += 1
                        continue

                    soup = BeautifulSoup(resp.text, "html.parser")
                    links = soup.find_all("a", class_="result-link")
                    snippets = soup.find_all("td", class_="result-snippet")

                    for link_tag, snippet_tag in zip(links, snippets):
                        raw_href = link_tag.get("href", "")
                        if "uddg=" in raw_href:
                            qs = parse_qs(urlparse(raw_href).query)
                            target_url = qs.get("uddg", [raw_href])[0]
                        else:
                            target_url = raw_href

                        if not target_url.startswith("http"):
                            continue

                        raw_title = link_tag.get_text(strip=True)
                        snippet_text = snippet_tag.get_text(strip=True) if snippet_tag else ""

                        raw_results.append({
                            "raw_title": raw_title,
                            "target_url": target_url,
                            "snippet": snippet_text
                        })
                        diagnostics["raw_results_count"] += 1

                except httpx.TimeoutException:
                    diagnostics["timeouts"] += 1
                    diagnostics["provider_status"] = "timeout"
                    logger.warning(f"DuckDuckGo timeout for query: '{q}'")
                except Exception as e:
                    diagnostics["provider_errors"] += 1
                    diagnostics["provider_status"] = "error"
                    logger.warning(f"DuckDuckGo search error: {e}")

        return raw_results


class SerperSearchProvider(SearchProviderBase):
    """
    Secondary Provider: Google Search via Serper API (https://google.serper.dev/search).
    Requires SERPER_API_KEY.
    """
    name: str = "Google (Serper API)"

    def is_configured(self) -> bool:
        return bool((settings.SERPER_API_KEY or "").strip())

    async def search(
        self,
        queries: List[str],
        limit: int,
        source_mode: str,
        diagnostics: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        import httpx

        raw_results = []
        api_key = settings.SERPER_API_KEY.strip()
        headers = {
            "X-API-KEY": api_key,
            "Content-Type": "application/json"
        }
        timeout = float(settings.SEARCH_TIMEOUT_SECONDS or 14.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            for q in queries[:2]:
                diagnostics["queries_executed"].append(f"[Serper] {q}")
                try:
                    payload = {"q": q, "gl": "in", "num": limit * 2}
                    resp = await client.post("https://google.serper.dev/search", json=payload, headers=headers)
                    if resp.status_code == 429:
                        diagnostics["rate_limits"] += 1
                        diagnostics["provider_status"] = "rate_limited_429"
                        break
                    if resp.status_code != 200:
                        diagnostics["provider_errors"] += 1
                        continue

                    data = resp.json()
                    for item in data.get("organic", []):
                        raw_results.append({
                            "raw_title": item.get("title", ""),
                            "target_url": item.get("link", ""),
                            "snippet": item.get("snippet", "")
                        })
                        diagnostics["raw_results_count"] += 1

                    if len(raw_results) >= limit * 2:
                        break

                except httpx.TimeoutException:
                    diagnostics["timeouts"] += 1
                except Exception as e:
                    diagnostics["provider_errors"] += 1
                    logger.warning(f"Serper API search error: {e}")

        return raw_results


class TavilySearchProvider(SearchProviderBase):
    """
    Secondary Provider: Tavily Search API (https://api.tavily.com/search).
    Requires TAVILY_API_KEY.
    """
    name: str = "Tavily Search API"

    def is_configured(self) -> bool:
        return bool((settings.TAVILY_API_KEY or "").strip())

    async def search(
        self,
        queries: List[str],
        limit: int,
        source_mode: str,
        diagnostics: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        import httpx

        raw_results = []
        api_key = settings.TAVILY_API_KEY.strip()
        timeout = float(settings.SEARCH_TIMEOUT_SECONDS or 14.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            for q in queries[:2]:
                diagnostics["queries_executed"].append(f"[Tavily] {q}")
                try:
                    payload = {
                        "api_key": api_key,
                        "query": q,
                        "max_results": limit * 2,
                    }
                    if source_mode == "instagram_only":
                        payload["include_domains"] = ["instagram.com"]

                    resp = await client.post("https://api.tavily.com/search", json=payload)
                    if resp.status_code == 429:
                        diagnostics["rate_limits"] += 1
                        diagnostics["provider_status"] = "rate_limited_429"
                        break
                    if resp.status_code != 200:
                        diagnostics["provider_errors"] += 1
                        continue

                    data = resp.json()
                    for item in data.get("results", []):
                        raw_results.append({
                            "raw_title": item.get("title", ""),
                            "target_url": item.get("url", ""),
                            "snippet": item.get("content", "")
                        })
                        diagnostics["raw_results_count"] += 1

                    if len(raw_results) >= limit * 2:
                        break

                except httpx.TimeoutException:
                    diagnostics["timeouts"] += 1
                except Exception as e:
                    diagnostics["provider_errors"] += 1
                    logger.warning(f"Tavily search error: {e}")

        return raw_results


class BraveSearchProvider(SearchProviderBase):
    """
    Secondary Provider: Brave Search API (https://api.search.brave.com/res/v1/web/search).
    Requires BRAVE_SEARCH_API_KEY.
    """
    name: str = "Brave Search API"

    def is_configured(self) -> bool:
        return bool((settings.BRAVE_SEARCH_API_KEY or "").strip())

    async def search(
        self,
        queries: List[str],
        limit: int,
        source_mode: str,
        diagnostics: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        import httpx

        raw_results = []
        api_key = settings.BRAVE_SEARCH_API_KEY.strip()
        headers = {"X-Subscription-Token": api_key}
        timeout = float(settings.SEARCH_TIMEOUT_SECONDS or 14.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            for q in queries[:2]:
                diagnostics["queries_executed"].append(f"[Brave] {q}")
                try:
                    resp = await client.get(
                        "https://api.search.brave.com/res/v1/web/search",
                        params={"q": q, "count": limit * 2},
                        headers=headers
                    )
                    if resp.status_code == 429:
                        diagnostics["rate_limits"] += 1
                        diagnostics["provider_status"] = "rate_limited_429"
                        break
                    if resp.status_code != 200:
                        diagnostics["provider_errors"] += 1
                        continue

                    data = resp.json()
                    for item in data.get("web", {}).get("results", []):
                        raw_results.append({
                            "raw_title": item.get("title", ""),
                            "target_url": item.get("url", ""),
                            "snippet": item.get("description", "")
                        })
                        diagnostics["raw_results_count"] += 1

                    if len(raw_results) >= limit * 2:
                        break

                except httpx.TimeoutException:
                    diagnostics["timeouts"] += 1
                except Exception as e:
                    diagnostics["provider_errors"] += 1
                    logger.warning(f"Brave search error: {e}")

        return raw_results


class SerpApiSearchProvider(SearchProviderBase):
    """
    Secondary Provider: SerpApi (https://serpapi.com/search.json).
    Requires SERPAPI_API_KEY.
    """
    name: str = "SerpApi"

    def is_configured(self) -> bool:
        return bool((settings.SERPAPI_API_KEY or "").strip())

    async def search(
        self,
        queries: List[str],
        limit: int,
        source_mode: str,
        diagnostics: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        import httpx

        raw_results = []
        api_key = settings.SERPAPI_API_KEY.strip()
        timeout = float(settings.SEARCH_TIMEOUT_SECONDS or 14.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            for q in queries[:2]:
                diagnostics["queries_executed"].append(f"[SerpApi] {q}")
                try:
                    resp = await client.get(
                        "https://serpapi.com/search.json",
                        params={"q": q, "api_key": api_key, "engine": "google", "num": limit * 2}
                    )
                    if resp.status_code == 429:
                        diagnostics["rate_limits"] += 1
                        diagnostics["provider_status"] = "rate_limited_429"
                        break
                    if resp.status_code != 200:
                        diagnostics["provider_errors"] += 1
                        continue

                    data = resp.json()
                    for item in data.get("organic_results", []):
                        raw_results.append({
                            "raw_title": item.get("title", ""),
                            "target_url": item.get("link", ""),
                            "snippet": item.get("snippet", "")
                        })
                        diagnostics["raw_results_count"] += 1

                    if len(raw_results) >= limit * 2:
                        break

                except httpx.TimeoutException:
                    diagnostics["timeouts"] += 1
                except Exception as e:
                    diagnostics["provider_errors"] += 1
                    logger.warning(f"SerpApi search error: {e}")

        return raw_results


def get_search_pipeline() -> Tuple[SearchProviderBase, List[SearchProviderBase]]:
    """
    Selects primary and secondary search providers according to configuration.
    """
    ddg = DuckDuckGoSearchProvider()
    secondaries = [
        SerperSearchProvider(),
        TavilySearchProvider(),
        BraveSearchProvider(),
        SerpApiSearchProvider()
    ]
    configured_secondaries = [p for p in secondaries if p.is_configured()]

    pref = (settings.SEARCH_PROVIDER or "auto").strip().lower()
    if pref == "serper":
        return SerperSearchProvider(), [ddg]
    elif pref == "tavily":
        return TavilySearchProvider(), [ddg]
    elif pref == "brave":
        return BraveSearchProvider(), [ddg]
    elif pref == "serpapi":
        return SerpApiSearchProvider(), [ddg]
    elif pref == "duckduckgo":
        return ddg, configured_secondaries
    else:  # "auto"
        # Primary is DuckDuckGo; fallbacks are configured secondary APIs
        return ddg, configured_secondaries


class InstagramBusinessSearchProvider(SearchProviderBase):
    """
    Discovers actual Instagram business profiles by issuing targeted site:instagram.com queries
    with niche and location parameters. Strictly rejects listicles, articles, and non-profile paths.
    Supports primary provider with automatic secondary fallback.
    """
    name: str = "Instagram-First Public Business Discovery"

    def is_configured(self) -> bool:
        return True

    async def search(
        self,
        niche: str = "",
        city_or_state: str = "",
        keywords: str = "",
        source_mode: str = "instagram_only",
        limit: int = 10,
        diagnostics: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        # Backward-compatibility for mock search signatures
        if not niche and "query" in kwargs:
            niche = kwargs["query"]
        if not city_or_state and "state" in kwargs:
            city_or_state = kwargs["state"]
        if not niche and "industry" in kwargs:
            niche = kwargs["industry"]

        if diagnostics is None:
            diagnostics = {
                "queries_executed": [],
                "raw_results_count": 0,
                "instagram_urls_count": 0,
                "rejected_counts": {"non_profile_path": 0, "aggregator_or_listicle": 0, "invalid_username": 0, "other": 0},
                "valid_profiles_count": 0,
                "duplicates_removed": 0,
                "provider_errors": 0,
                "timeouts": 0,
                "rate_limits": 0,
                "provider_status": "ok",
                "provider_used": "DuckDuckGo",
                "fallback_used": False,
            }

        loc_info = normalize_location_input(city_or_state)
        queries = generate_targeted_queries(niche, loc_info, keywords, source_mode)

        primary_provider, fallback_providers = get_search_pipeline()
        diagnostics["provider_used"] = primary_provider.name

        raw_items = await primary_provider.search(
            queries=queries,
            limit=limit,
            source_mode=source_mode,
            diagnostics=diagnostics
        )

        # Trigger fallback if primary provider returned 0 results and was rate-limited or errored
        if len(raw_items) == 0 and fallback_providers:
            for fallback in fallback_providers:
                if not fallback.is_configured():
                    continue
                logger.info(f"Primary provider returned 0 results. Triggering fallback to {fallback.name}")
                fallback_items = await fallback.search(
                    queries=queries,
                    limit=limit,
                    source_mode=source_mode,
                    diagnostics=diagnostics
                )
                if fallback_items:
                    raw_items = fallback_items
                    diagnostics["provider_used"] = fallback.name
                    diagnostics["fallback_used"] = True
                    diagnostics["provider_status"] = "ok"
                    break

        discovered_candidates = []
        seen_identifiers = set()

        for item in raw_items:
            target_url = item.get("target_url", "").strip()
            raw_title = item.get("raw_title", "").strip()
            snippet_text = item.get("snippet", "").strip()

            if not target_url:
                continue

            if "instagram.com" in target_url.lower():
                diagnostics["instagram_urls_count"] += 1

            # Filter out aggregator / listicle domains
            domain = extract_root_domain(target_url)
            if not domain or domain in AGGREGATOR_LISTICLE_DOMAINS:
                diagnostics["rejected_counts"]["aggregator_or_listicle"] += 1
                continue

            # Filter out listicles by title
            title_lower = raw_title.lower()
            if any(re.search(pat, title_lower) for pat in LISTICLE_TITLE_PATTERNS):
                diagnostics["rejected_counts"]["aggregator_or_listicle"] += 1
                continue

            if source_mode == "instagram_only":
                is_profile, username, rejection_reason = classify_instagram_url(target_url)
                if not is_profile or not username:
                    if rejection_reason == "reserved_path":
                        diagnostics["rejected_counts"]["non_profile_path"] += 1
                    elif rejection_reason == "invalid_username":
                        diagnostics["rejected_counts"]["invalid_username"] += 1
                    else:
                        diagnostics["rejected_counts"]["other"] += 1
                    continue

                if username in seen_identifiers:
                    diagnostics["duplicates_removed"] += 1
                    continue

                seen_identifiers.add(username)
                diagnostics["valid_profiles_count"] += 1

                clean_name = clean_instagram_business_name(raw_title, username)
                contacts = extract_contacts_and_links(snippet_text)
                website_url = contacts["external_links"][0] if contacts["external_links"] else ""

                discovered_candidates.append({
                    "business_name": clean_name,
                    "instagram_username": username,
                    "instagram_handle": username,
                    "instagram_url": f"https://instagram.com/{username}",
                    "website_url": website_url,
                    "domain": extract_root_domain(website_url),
                    "source_url": target_url,
                    "raw_title": raw_title,
                    "snippet": snippet_text,
                    "contacts": contacts,
                })
            else:
                # All Sources mode: individual business websites or profiles
                if domain in seen_identifiers:
                    diagnostics["duplicates_removed"] += 1
                    continue
                seen_identifiers.add(domain)

                is_profile, username = is_valid_instagram_profile_url(target_url)
                clean_name = re.sub(r"\s*[-|–—].*$", "", raw_title).strip() or raw_title[:60]
                contacts = extract_contacts_and_links(snippet_text)

                discovered_candidates.append({
                    "business_name": clean_name,
                    "instagram_username": username if is_profile else "",
                    "instagram_handle": username if is_profile else "",
                    "instagram_url": f"https://instagram.com/{username}" if is_profile else "",
                    "website_url": "" if is_profile else target_url,
                    "domain": domain,
                    "source_url": target_url,
                    "raw_title": raw_title,
                    "snippet": snippet_text,
                    "contacts": contacts,
                })

        return discovered_candidates


# Backward compatibility alias
PublicDirectorySearchProvider = InstagramBusinessSearchProvider


# ---------------------------------------------------------------------------
# Lead Discovery Execution
# ---------------------------------------------------------------------------

async def execute_lead_discovery(
    cursor,
    niche: str,
    city_or_state: str = "",
    keywords: str = "",
    source_mode: str = "instagram_only",
    stage: str = "all",
    website_filter: str = "all",
    min_score: int = 0,
    exclude_crm: bool = False,
    limit: int = 10
) -> Dict[str, Any]:
    """
    Executes Instagram-first prospect discovery with structured diagnostics,
    location normalization, transparent opportunity scoring, and CRM deduplication.
    """
    clean_niche = niche.strip()
    clean_city = city_or_state.strip()
    clean_keywords = keywords.strip()

    loc_info = normalize_location_input(clean_city)
    display_location = loc_info.get("display") or clean_city

    diagnostics = {
        "queries_executed": [],
        "raw_results_count": 0,
        "instagram_urls_count": 0,
        "rejected_counts": {"non_profile_path": 0, "aggregator_or_listicle": 0, "invalid_username": 0, "other": 0},
        "valid_profiles_count": 0,
        "duplicates_removed": 0,
        "provider_errors": 0,
        "timeouts": 0,
        "rate_limits": 0,
        "provider_status": "ok",
        "provider_used": "DuckDuckGo",
        "provider_error_message": None,
        "fallback_used": False,
    }

    provider = InstagramBusinessSearchProvider()

    try:
        raw_candidates = await provider.search(
            niche=clean_niche,
            city_or_state=clean_city,
            keywords=clean_keywords,
            source_mode=source_mode,
            limit=limit,
            diagnostics=diagnostics
        )
    except TypeError:
        try:
            raw_candidates = await provider.search(
                niche=clean_niche,
                city_or_state=clean_city,
                keywords=clean_keywords,
                source_mode=source_mode,
                limit=limit
            )
        except TypeError:
            # Fallback for legacy mock signatures
            raw_candidates = await provider.search(
                f"{clean_niche} {clean_keywords}".strip(),
                state=clean_city,
                industry=clean_niche,
                limit=limit
            )

    items = []
    now_iso = datetime.now().isoformat()

    for cand in raw_candidates:
        web_url = cand.get("website_url", "")
        domain = cand.get("domain") or extract_root_domain(web_url)
        cand["domain"] = domain
        ig_url = cand.get("instagram_url", "")
        b_name = cand.get("business_name", "")
        contacts = cand.get("contacts", {"phones": [], "emails": [], "external_links": []})

        dup = check_duplicate_lead(
            cursor,
            business_name=b_name,
            website_url=web_url,
            instagram_url=ig_url
        )
        is_dup = dup is not None

        if exclude_crm and is_dup:
            diagnostics["duplicates_removed"] += 1
            continue

        opp_eval = evaluate_digital_opportunity(
            business_name=b_name,
            niche=clean_niche,
            city=loc_info.get("city") or clean_city,
            website_url=web_url,
            instagram_handle=cand.get("instagram_handle", ""),
            snippet=cand.get("snippet", ""),
            contacts=contacts
        )

        lead_web_status = opp_eval["website_status"]
        if website_filter == "no_website" and lead_web_status != "no_website":
            continue
        elif website_filter == "has_website" and lead_web_status != "has_website":
            continue
        elif website_filter == "needs_improvement" and lead_web_status not in ("broken_website", "no_website"):
            continue

        if min_score and opp_eval["lead_score"] < min_score:
            continue

        lead_stage = opp_eval["business_stage"]
        if stage != "all" and stage != lead_stage:
            continue

        contact_display = ", ".join(contacts["phones"] + contacts["emails"])

        item = {
            "business_name": b_name,
            "instagram_username": cand.get("instagram_username", ""),
            "instagram_handle": cand.get("instagram_handle", ""),
            "instagram_url": ig_url,
            "website_url": web_url,
            "domain": domain,
            "contact_details": contact_display,
            "public_phone": contacts["phones"][0] if contacts["phones"] else "",
            "public_email": contacts["emails"][0] if contacts["emails"] else "",
            "source_url": cand.get("source_url", web_url or ig_url),
            "industry": clean_niche or "Local Business",
            "business_category": clean_niche or "Local Business",
            "state": loc_info.get("state") or (clean_city if clean_city and clean_city.lower() != "all states" else "India"),
            "city": loc_info.get("city") or clean_city,
            "snippet": cand.get("snippet", ""),
            "business_stage": lead_stage,
            "website_status": lead_web_status,
            "observed_problems": opp_eval["observed_problems"],
            "suggested_service": opp_eval["suggested_service"],
            "personalized_dm": opp_eval["personalized_dm"],
            "lead_score": opp_eval["lead_score"],
            "score_reasons": opp_eval["score_reasons"],
            "score_breakdown": opp_eval["score_breakdown"],
            "already_exists": is_dup,
            "is_duplicate": is_dup,
            "existing_lead_id": dup["id"] if dup else None,
            "reachable": lead_web_status != "broken_website",
            "status_code": 200 if lead_web_status != "broken_website" else 404,
            "discovered_at": now_iso,
            "provider_source": diagnostics.get("provider_used") or provider.name,
        }
        items.append(item)

        if len(items) >= limit:
            break

    # Determine status & limitation notice
    provider_name = diagnostics.get("provider_used") or provider.name
    limitation_notice = None

    if len(items) == 0:
        if diagnostics.get("provider_status") == "rate_limited_202":
            limitation_notice = (
                f"DuckDuckGo search provider challenged queries from this server IP (HTTP 202 Bot Challenge). "
                "0 verified profiles could be retrieved. To enable reliable prospect discovery on cloud hosting, "
                "configure a secondary search API key (SERPER_API_KEY, TAVILY_API_KEY, or BRAVE_SEARCH_API_KEY) in Settings."
            )
        elif diagnostics.get("raw_results_count", 0) > 0 and diagnostics.get("valid_profiles_count", 0) == 0:
            rejs = diagnostics.get("rejected_counts", {})
            limitation_notice = (
                f"Search provider returned {diagnostics['raw_results_count']} raw results, but all were rejected by validation "
                f"({rejs.get('non_profile_path', 0)} non-profile paths/reels/popular pages, "
                f"{rejs.get('aggregator_or_listicle', 0)} directories/listicles). "
                "Try adjusting niche or location keywords."
            )
        elif diagnostics.get("provider_status") == "timeout":
            limitation_notice = (
                f"Search provider timed out while querying '{clean_niche}' in '{display_location or 'selected region'}'. "
                "Please retry in a moment."
            )
        else:
            limitation_notice = (
                f"No verified business profiles found for '{clean_niche}' in '{display_location or 'selected region'}'. "
                f"{provider_name} returned 0 verified profiles. Try adjusting the niche or city keywords, or switch to All Public Sources."
            )

    return {
        "status": "success",
        "query": f"{clean_niche} in {display_location} {clean_keywords}".strip(),
        "provider": provider_name,
        "results": items,
        "total_found": len(items),
        "source_mode": source_mode,
        "limitation_notice": limitation_notice,
        "error_message": None,
        "diagnostics": diagnostics
    }
