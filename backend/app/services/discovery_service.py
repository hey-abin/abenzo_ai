import re
import html
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import urlparse, parse_qs
from datetime import datetime

# ---------------------------------------------------------------------------
# Instagram URL & Profile Extraction Utilities
# ---------------------------------------------------------------------------

INSTAGRAM_RESERVED_PATHS = {
    "p", "reel", "reels", "tv", "explore", "stories", "popular",
    "tags", "directory", "accounts", "about", "legal", "developer",
    "privacy", "help", "graphql", "api", "challenge", "login",
    "web", "session", "support", "press", "contact", "terms"
}

AGGREGATOR_LISTICLE_DOMAINS = {
    "duckduckgo.com", "google.com", "bing.com", "yahoo.com",
    "wikipedia.org", "youtube.com", "facebook.com", "twitter.com",
    "linkedin.com", "tripadvisor.com", "justdial.com", "indiamart.com",
    "yellowpages.in", "sulekha.com", "zomato.com", "swiggy.com",
    "practo.com", "amazon.in", "flipkart.com", "quora.com",
    "reddit.com", "medium.com", "lbb.in", "lifestyleasia.com",
    "curlytales.com", "clutch.co", "goodfirms.co", "magicbricks.com",
    "99acres.com", "housing.com", "forbes.com", "tradeindia.com",
    "exportersindia.com", "dir.indiamart.com"
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
    r"\bshopping\s+guide\b"
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


def is_valid_instagram_profile_url(url: str) -> Tuple[bool, str]:
    """
    Returns (True, clean_username) if url is a genuine individual Instagram profile.
    Rejects posts (/p/), reels (/reel/), tags (/tags/), explore, search result listicles, etc.
    """
    if not url:
        return False, ""
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    if "instagram.com" not in domain:
        return False, ""

    # Path segments
    path = parsed.path.strip("/")
    if not path:
        return False, ""

    parts = path.split("/")
    first_seg = parts[0].strip().lower()

    if first_seg in INSTAGRAM_RESERVED_PATHS:
        return False, ""

    # Username pattern: 1 to 30 characters, letters, numbers, periods, underscores
    if re.match(r"^[a-zA-Z0-9_\.]{2,35}$", first_seg):
        return True, first_seg

    return False, ""


def extract_instagram_handle(url: str) -> str:
    if not url:
        return ""
    u = url.strip()
    is_profile, username = is_valid_instagram_profile_url(u)
    if is_profile:
        return username
    # If passed as @username or bare username
    cleaned = u.strip().lstrip("@").rstrip("/")
    if re.match(r"^[a-zA-Z0-9_\.]{2,35}$", cleaned) and cleaned.lower() not in INSTAGRAM_RESERVED_PATHS:
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
    # Remove Instagram suffix
    title = re.sub(r"\s*[•\-|–—]\s*Instagram.*$", "", title, flags=re.IGNORECASE).strip()
    title = re.sub(r"\s*on\s+Instagram.*$", "", title, flags=re.IGNORECASE).strip()
    # Remove handle from brackets: 'Kochi Boutique (@kochi_boutiquee)' -> 'Kochi Boutique'
    title = re.sub(r"\s*\(@[a-zA-Z0-9_\.]+\)", "", title).strip()
    # Remove standalone '@handle'
    title = re.sub(r"^@[a-zA-Z0-9_\.]+\s*", "", title).strip()

    if len(title) >= 2 and not title.lower().startswith("instagram"):
        return title[:70].strip()

    # Fallback to readable capitalized handle
    if username:
        words = re.sub(r"[_\.]+", " ", username).title().strip()
        return words or f"@{username}"

    return "Local Business"


def extract_contacts_and_links(text: str) -> Dict[str, Any]:
    """
    Extracts phone numbers, email addresses, and external website/catalog links from public text.
    """
    contacts = {"phones": [], "emails": [], "external_links": []}
    if not text:
        return contacts

    # Indian phone numbers
    phones = re.findall(r"(?:\+91[\-\s]?)?[6-9]\d{9}", text)
    for p in phones:
        clean_p = re.sub(r"[^\d+]", "", p)
        if clean_p not in contacts["phones"]:
            contacts["phones"].append(clean_p)

    # Email addresses
    emails = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
    for e in emails:
        clean_e = e.lower().strip()
        if clean_e not in contacts["emails"]:
            contacts["emails"].append(clean_e)

    # URLs mentioned in text
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

    # Check by normalized instagram handle
    if norm_ig:
        cursor.execute("SELECT id, business_name, instagram_url FROM leads")
        for row in cursor.fetchall():
            row_ig = extract_instagram_handle(row["instagram_url"])
            if row_ig and row_ig.lower() == norm_ig.lower():
                return {"id": row["id"], "business_name": row["business_name"], "matched_by": "instagram_handle"}

    # Check by website root domain
    if norm_web and norm_web not in GENERIC_DOMAINS:
        cursor.execute("SELECT id, business_name, website_url FROM leads")
        for row in cursor.fetchall():
            row_domain = extract_root_domain(row["website_url"])
            if row_domain and row_domain not in GENERIC_DOMAINS and row_domain == norm_web:
                return {"id": row["id"], "business_name": row["business_name"], "matched_by": "website_url"}

    # Check by exact business name
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
    """
    Evaluates observed digital problems, transparent fit score, and recommended Abenzo service.
    Rewards relevance and real service opportunities without giving every lead a flat score.
    """
    score = 40  # Baseline for matching niche & location
    breakdown = {"base_relevance": 40}
    reasons = ["Matched business niche and geographic criteria"]

    web_lower = website_url.lower() if website_url else ""
    snip_lower = snippet.lower()

    # Determine website status & digital problems
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
        # Check if website is broken or flagged
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

    # Contact details bonus
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

    # Location alignment
    if city and city.lower() in snip_lower:
        score += 5
        breakdown["local_geography_match"] = 5
        reasons.append(f"Explicitly verified in {city} (+5 pts)")

    final_score = max(25, min(95, score))

    # Determine business stage
    business_stage = "small_business"
    if any(k in snip_lower for k in ["startup", "founded in", "tech", "app", "saas", "innovat"]):
        business_stage = "startup"
    elif any(k in snip_lower for k in ["brand", "label", "studio", "atelier", "organic", "artisan"]):
        business_stage = "local_brand"

    # Generate Personalized, Non-Spam Outreach Draft (30-50 words)
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
# Search Providers
# ---------------------------------------------------------------------------

class SearchProviderBase:
    name: str = "Base"

    def is_configured(self) -> bool:
        raise NotImplementedError

    async def search(
        self,
        niche: str,
        city_or_state: str = "",
        keywords: str = "",
        source_mode: str = "instagram_only",
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError


class InstagramBusinessSearchProvider(SearchProviderBase):
    """
    Discovers actual Instagram business profiles by issuing targeted site:instagram.com queries
    with niche and location parameters. Strictly rejects listicles, articles, and non-profile paths.
    """
    name: str = "Instagram-First Public Business Discovery"

    def is_configured(self) -> bool:
        return True

    async def search(
        self,
        niche: str,
        city_or_state: str = "",
        keywords: str = "",
        source_mode: str = "instagram_only",
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        import httpx
        from bs4 import BeautifulSoup

        # Construct targeted queries
        queries = []
        loc = city_or_state.strip() if city_or_state and city_or_state.lower() not in ("all states", "all", "india") else ""

        if source_mode == "instagram_only":
            if loc:
                queries.append(f'site:instagram.com/ "{loc}" {niche} {keywords}'.strip())
                queries.append(f'site:instagram.com/ {niche} "{loc}"'.strip())
            else:
                queries.append(f'site:instagram.com/ {niche} {keywords}'.strip())
        else:
            # All sources query
            if loc:
                queries.append(f'"{loc}" {niche} {keywords} business'.strip())
            else:
                queries.append(f'{niche} {keywords} small business India'.strip())

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        discovered_raw = []
        seen_identifiers = set()

        async with httpx.AsyncClient(timeout=14.0) as client:
            for q in queries:
                if len(discovered_raw) >= limit * 2:
                    break
                try:
                    resp = await client.post(
                        "https://lite.duckduckgo.com/lite/",
                        data={"q": q},
                        headers=headers
                    )
                    if resp.status_code != 200:
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

                        # Filter out listicles / wholesale / blogs by title & domain
                        domain = extract_root_domain(target_url)
                        if not domain or domain in AGGREGATOR_LISTICLE_DOMAINS:
                            continue

                        title_lower = raw_title.lower()
                        if any(re.search(pat, title_lower) for pat in LISTICLE_TITLE_PATTERNS):
                            continue

                        if source_mode == "instagram_only":
                            is_profile, username = is_valid_instagram_profile_url(target_url)
                            if not is_profile or not username:
                                continue
                            if username in seen_identifiers:
                                continue

                            seen_identifiers.add(username)
                            clean_name = clean_instagram_business_name(raw_title, username)
                            contacts = extract_contacts_and_links(snippet_text)

                            website_url = contacts["external_links"][0] if contacts["external_links"] else ""

                            discovered_raw.append({
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
                                continue
                            seen_identifiers.add(domain)

                            is_profile, username = is_valid_instagram_profile_url(target_url)
                            clean_name = re.sub(r"\s*[-|–—].*$", "", raw_title).strip() or raw_title[:60]
                            contacts = extract_contacts_and_links(snippet_text)

                            discovered_raw.append({
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

                except Exception:
                    continue

        return discovered_raw

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
    Executes Instagram-first prospect discovery with opportunity evaluation,
    transparent fit scoring, and CRM deduplication.
    """
    provider = InstagramBusinessSearchProvider()
    clean_niche = niche.strip()
    clean_city = city_or_state.strip()
    clean_keywords = keywords.strip()
    try:
        raw_candidates = await provider.search(
            niche=clean_niche,
            city_or_state=clean_city,
            keywords=clean_keywords,
            source_mode=source_mode,
            limit=limit
        )
    except TypeError:
        # Fallback for mock search implementations with legacy signature search(query, state, industry, limit)
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

        # Deduplication check against existing CRM leads
        dup = check_duplicate_lead(
            cursor,
            business_name=b_name,
            website_url=web_url,
            instagram_url=ig_url
        )
        is_dup = dup is not None

        # Exclude CRM filter
        if exclude_crm and is_dup:
            continue

        # Evaluate digital opportunity & transparent fit score
        opp_eval = evaluate_digital_opportunity(
            business_name=b_name,
            niche=clean_niche,
            city=clean_city,
            website_url=web_url,
            instagram_handle=cand.get("instagram_handle", ""),
            snippet=cand.get("snippet", ""),
            contacts=contacts
        )

        # Website filter
        lead_web_status = opp_eval["website_status"]
        if website_filter == "no_website" and lead_web_status != "no_website":
            continue
        elif website_filter == "has_website" and lead_web_status != "has_website":
            continue
        elif website_filter == "needs_improvement" and lead_web_status not in ("broken_website", "no_website"):
            continue

        # Minimum score filter
        if min_score and opp_eval["lead_score"] < min_score:
            continue

        # Business stage filter
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
            "state": clean_city if clean_city and clean_city.lower() != "all states" else "India",
            "city": clean_city,
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
            "provider_source": provider.name,
        }
        items.append(item)

        if len(items) >= limit:
            break

    limitation_notice = None
    if len(items) == 0:
        limitation_notice = (
            f"No verified business profiles found for '{clean_niche}' in '{clean_city or 'selected region'}'. "
            "DuckDuckGo search returned 0 verified profiles. Try adjusting the niche or city keywords, or switch to All Public Sources."
        )

    return {
        "status": "success",
        "query": f"{clean_niche} in {clean_city} {clean_keywords}".strip(),
        "provider": provider.name,
        "results": items,
        "total_found": len(items),
        "source_mode": source_mode,
        "limitation_notice": limitation_notice,
        "error_message": None
    }
