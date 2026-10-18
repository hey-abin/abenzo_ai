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
    async def search(self, query: str, state: str = "", industry: str = "") -> List[Dict[str, Any]]:
        raise NotImplementedError

class PermittedDirectoryProvider(SearchProviderBase):
    """
    Search provider interface for permitted directory / search APIs.
    Follows Rule: Do not fake discovery results if no provider is configured.
    """
    name: str = "Permitted Search Provider"

    def is_configured(self) -> bool:
        return False

    async def search(self, query: str, state: str = "", industry: str = "") -> List[Dict[str, Any]]:
        # As required by spec: Never fake results when a provider is not configured.
        return []
