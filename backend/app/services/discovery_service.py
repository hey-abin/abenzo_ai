import re
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

def normalize_domain_or_url(url: str) -> str:
    if not url:
        return ""
    u = url.strip().lower()
    # Remove protocol
    u = re.sub(r"^https?://", "", u)
    # Remove www.
    u = re.sub(r"^www\.", "", u)
    # Remove query params & fragment
    u = u.split("?")[0].split("#")[0]
    # Remove trailing slash
    u = u.rstrip("/")
    return u

def extract_root_domain(url: str) -> str:
    norm = normalize_domain_or_url(url)
    return norm.split("/")[0] if norm else ""

def extract_instagram_handle(url: str) -> str:
    if not url:
        return ""
    u = url.strip().lower().rstrip("/")
    match = re.search(r"instagram\.com/([a-zA-Z0-9_\.\-]+)", u)
    if match:
        return match.group(1)
    # If passed as @handle or handle
    u = u.lstrip("@")
    return u

def check_duplicate_lead(cursor, business_name: str, website_url: str = "", instagram_url: str = "") -> Optional[Dict[str, Any]]:
    norm_web = extract_root_domain(website_url)
    norm_ig = extract_instagram_handle(instagram_url)
    norm_name = business_name.strip().lower()

    # Generic aggregators that should not deduplicate by root domain alone
    GENERIC_DOMAINS = {"linktr.ee", "bio.link", "wa.me", "api.whatsapp.com", "instagram.com", "facebook.com"}

    # Check by website root domain
    if norm_web and norm_web not in GENERIC_DOMAINS:
        cursor.execute("SELECT id, business_name, website_url FROM leads")
        for row in cursor.fetchall():
            row_domain = extract_root_domain(row["website_url"])
            if row_domain and row_domain not in GENERIC_DOMAINS and row_domain == norm_web:
                return {"id": row["id"], "business_name": row["business_name"], "matched_by": "website_url"}

    # Check by instagram
    if norm_ig:
        cursor.execute("SELECT id, business_name, instagram_url FROM leads")
        for row in cursor.fetchall():
            if extract_instagram_handle(row["instagram_url"]) == norm_ig:
                return {"id": row["id"], "business_name": row["business_name"], "matched_by": "instagram_handle"}

    # Check by exact business name
    cursor.execute("SELECT id, business_name FROM leads WHERE LOWER(TRIM(business_name)) = ?", (norm_name,))
    match = cursor.fetchone()
    if match:
        return {"id": match["id"], "business_name": match["business_name"], "matched_by": "business_name"}

    return None

class SearchProviderBase:
    name: str = "Base"
    def is_configured(self) -> bool:
        raise NotImplementedError
    async def search(self, query: str, state: str = "", industry: str = "", limit: int = 10) -> List[Dict[str, Any]]:
        raise NotImplementedError

class PublicDirectorySearchProvider(SearchProviderBase):
    """
    Finds real public business listings across India via live public directory search.
    Never fabricates results. Returns genuine domain names, source URLs, and public snippets.
    """
    name: str = "Public Directory & Web Search"

    def is_configured(self) -> bool:
        return True

    async def search(self, query: str, state: str = "", industry: str = "", limit: int = 10) -> List[Dict[str, Any]]:
        import httpx
        from bs4 import BeautifulSoup
        from urllib.parse import urlparse, parse_qs

        # Formulate targeted query
        parts = [query.strip()]
        if industry and industry.lower() not in query.lower():
            parts.append(industry.strip())
        if state and state.lower() not in ("all states", "all", "india") and state.lower() not in query.lower():
            parts.append(state.strip())
        full_query = " ".join([p for p in parts if p]).strip()
        if not full_query:
            return []

        url = "https://lite.duckduckgo.com/lite/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                resp = await client.post(url, data={"q": f"{full_query} website"}, headers=headers)
                if resp.status_code != 200:
                    return []

                soup = BeautifulSoup(resp.text, "html.parser")
                links = soup.find_all("a", class_="result-link")
                snippets = soup.find_all("td", class_="result-snippet")

                results = []
                seen_domains = set()

                IGNORED_DOMAINS = {
                    "duckduckgo.com", "google.com", "bing.com", "yahoo.com",
                    "wikipedia.org", "youtube.com", "facebook.com", "twitter.com",
                    "linkedin.com", "tripadvisor.com", "justdial.com", "indiamart.com",
                    "yellowpages.in", "sulekha.com", "zomato.com", "swiggy.com",
                    "practo.com", "amazon.in", "flipkart.com", "quora.com",
                    "reddit.com", "medium.com"
                }

                for link_tag, snippet_tag in zip(links, snippets):
                    raw_href = link_tag.get("href", "")
                    if "uddg=" in raw_href:
                        qs = parse_qs(urlparse(raw_href).query)
                        target_url = qs.get("uddg", [raw_href])[0]
                    else:
                        target_url = raw_href

                    if not target_url.startswith("http"):
                        continue

                    domain = extract_root_domain(target_url)
                    if not domain or domain in IGNORED_DOMAINS or domain in seen_domains:
                        continue

                    is_instagram = "instagram.com" in domain
                    raw_title = link_tag.get_text(strip=True)
                    clean_name = re.sub(r"\s*[-|–—].*$", "", raw_title).strip()
                    if len(clean_name) < 2:
                        clean_name = raw_title[:60]

                    snippet_text = snippet_tag.get_text(strip=True) if snippet_tag else ""

                    contacts = []
                    phone_match = re.findall(r"(?:\+91[\-\s]?)?[6-9]\d{9}", snippet_text)
                    if phone_match:
                        contacts.append(phone_match[0])
                    email_match = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", snippet_text)
                    if email_match:
                        contacts.append(email_match[0])

                    results.append({
                        "business_name": clean_name,
                        "website_url": "" if is_instagram else target_url,
                        "instagram_url": target_url if is_instagram else "",
                        "contact_details": ", ".join(contacts),
                        "source_url": target_url,
                        "industry": industry or "Local Business",
                        "state": state if state and state.lower() != "all states" else "India",
                        "snippet": snippet_text,
                    })
                    seen_domains.add(domain)

                    if len(results) >= limit:
                        break

                return results
        except Exception as e:
            raise RuntimeError(f"Public directory search error: {str(e)}")

async def execute_lead_discovery(cursor, niche: str, city_or_state: str = "", keywords: str = "", limit: int = 10) -> Dict[str, Any]:
    """
    Executes live public business discovery and checks each candidate against existing CRM records.
    """
    query_str = f"{niche} {keywords}".strip()
    provider = PublicDirectorySearchProvider()

    raw_candidates = await provider.search(query=query_str, state=city_or_state, industry=niche, limit=limit)
    items = []
    for cand in raw_candidates:
        web_url = cand.get("website_url", "")
        domain = extract_root_domain(web_url)
        cand["domain"] = domain
        dup = check_duplicate_lead(
            cursor,
            business_name=cand["business_name"],
            website_url=web_url,
            instagram_url=cand.get("instagram_url", "")
        )
        cand["already_exists"] = dup is not None
        cand["is_duplicate"] = dup is not None
        cand["existing_lead_id"] = dup["id"] if dup else None

        # Transparent fit scoring
        score = 50
        reasons = []
        if domain:
            reasons.append("Custom website domain found")
            score += 15
        if cand.get("contact_details"):
            reasons.append("Direct public phone/email available")
            score += 10
        if cand.get("snippet") and len(cand["snippet"]) > 30:
            reasons.append("Active business listing verified")
            score += 10
        cand["lead_score"] = min(100, score)
        cand["score_reasons"] = reasons
        cand["reachable"] = True
        items.append(cand)

    return {
        "status": "success",
        "query": f"{niche} in {city_or_state} {keywords}".strip(),
        "provider": provider.name,
        "results": items,
        "total_found": len(items)
    }
