import httpx
from bs4 import BeautifulSoup
from typing import Dict, Any
from urllib.parse import urlparse
from backend.app.schemas import WebsiteCheckResult

def normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url

async def check_website(url: str, timeout_seconds: float = 6.0) -> WebsiteCheckResult:
    if not url or not url.strip():
        return WebsiteCheckResult(
            url="",
            status="uncertain",
            evidence_summary="No website URL provided."
        )

    clean_url = normalize_url(url)
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True, verify=False) as client:
            resp = await client.get(clean_url, headers=headers)
            status_code = resp.status_code

            if status_code >= 200 and status_code < 300:
                html = resp.text
                soup = BeautifulSoup(html, "html.parser")
                title = soup.title.string.strip() if soup.title and soup.title.string else "Untitled"
                
                meta_desc = ""
                meta_tag = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
                if meta_tag and meta_tag.get("content"):
                    meta_desc = meta_tag["content"].strip()

                text_lower = soup.get_text().lower()
                has_contact = any(k in text_lower for k in ["contact", "enquiry", "inquiry", "whatsapp", "call us", "reach us"])
                has_ecommerce = any(k in text_lower for k in ["cart", "checkout", "buy now", "order now", "shop"])
                has_viewport = bool(soup.find("meta", attrs={"name": "viewport"}))

                is_https = str(resp.url).startswith("https://")
                summary = f"Website verified live (HTTP {status_code})."
                if is_https:
                    summary += " Valid HTTPS secured."
                summary += f" Title: '{title[:50]}'."
                if not has_viewport:
                    summary += " May lack modern responsive viewport tag."
                if not has_contact:
                    summary += " No obvious contact/inquiry form detected on homepage."
                if has_ecommerce:
                    summary += " E-commerce/ordering features present."

                return WebsiteCheckResult(
                    url=str(resp.url),
                    status="found",
                    status_code=status_code,
                    title=title,
                    meta_description=meta_desc[:200] if meta_desc else None,
                    has_contact_or_inquiry=has_contact,
                    is_mobile_responsive_indicated=has_viewport,
                    evidence_summary=summary,
                    raw_details={
                        "final_url": str(resp.url),
                        "is_https": is_https,
                        "has_ecommerce": has_ecommerce,
                        "title": title
                    }
                )
            elif status_code == 404:
                return WebsiteCheckResult(
                    url=clean_url,
                    status="broken_website",
                    status_code=status_code,
                    evidence_summary=f"Website unreachable: Domain returned HTTP 404 Not Found. Page or site may be inactive."
                )
            elif status_code >= 500:
                return WebsiteCheckResult(
                    url=clean_url,
                    status="broken_website",
                    status_code=status_code,
                    evidence_summary=f"Website unreachable: Server returned HTTP {status_code} internal error."
                )
            else:
                return WebsiteCheckResult(
                    url=clean_url,
                    status="uncertain",
                    status_code=status_code,
                    evidence_summary=f"Server returned HTTP {status_code}. Status is uncertain."
                )

    except httpx.ConnectError:
        return WebsiteCheckResult(
            url=clean_url,
            status="broken_website",
            evidence_summary="Website unreachable: Connection could not be established. Domain may not resolve or server is down."
        )
    except httpx.TimeoutException:
        return WebsiteCheckResult(
            url=clean_url,
            status="uncertain",
            evidence_summary="Website not assessed: Request timed out after 6 seconds. Website may be slow, geo-blocked, or rate-limited."
        )
    except Exception as e:
        return WebsiteCheckResult(
            url=clean_url,
            status="uncertain",
            evidence_summary=f"Website not assessed: Network check encountered {type(e).__name__}."
        )
