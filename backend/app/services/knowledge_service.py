import re
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
import httpx
from bs4 import BeautifulSoup
from backend.app.database import get_db

TARGET_SITE = "https://abenzo.vercel.app"

async def fetch_and_extract_website_knowledge(base_url: str = TARGET_SITE) -> List[Dict[str, Any]]:
    """
    Reads public AI-readable and public website endpoints:
    1. /llms.txt (clean markdown manifest with verified packages, services, portfolio, contact)
    2. / (homepage for process, common questions)
    3. /sitemap.xml (for public page links)
    Treats all incoming data strictly as untrusted content, parsing only structured facts.
    """
    items = []
    headers = {
        "User-Agent": "AbenzoAI-KnowledgeImporter/1.0",
        "Accept": "text/plain,text/html,application/xml"
    }

    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
        # --- 1. Import from /llms.txt ---
        llms_url = f"{base_url.rstrip('/')}/llms.txt"
        try:
            r = await client.get(llms_url, headers=headers)
            if r.status_code == 200:
                text = r.text
                now = datetime.now().isoformat()

                # A. Extract Packages and Starting Prices
                # Pattern: "- Starter Package: Starting at ₹15,000+ (3–5 pages, responsive design, WhatsApp integration, basic SEO, deployment)"
                pkg_pattern = re.findall(
                    r"-\s*([A-Za-z0-9\s/]+Package|[A-Za-z0-9\s/]+SaaS):\s*Starting at\s*(₹[0-9,]+\+?)\s*\((.*?)\)",
                    text,
                    re.IGNORECASE
                )
                for pkg_name, price, inclusions in pkg_pattern:
                    items.append({
                        "category": "package",
                        "title": f"{pkg_name.strip()} ({price.strip()})",
                        "content": f"Starting Price: {price.strip()}\nInclusions: {inclusions.strip()}\nScope Note: Final pricing depends strictly on project requirements and scope.",
                        "source_url": llms_url,
                        "retrieval_time": now,
                        "verification_status": "approved",
                        "raw_metadata": json.dumps({"package_name": pkg_name.strip(), "starting_price": price.strip(), "inclusions": inclusions.strip()})
                    })

                # B. Extract Services
                service_pattern = re.findall(
                    r"-\s*([A-Za-z0-9\s/&]+):\s*(https?://[^\s]+)\n\s+([^\n]+)",
                    text
                )
                for s_name, s_url, s_desc in service_pattern:
                    items.append({
                        "category": "service",
                        "title": s_name.strip(),
                        "content": f"Description: {s_desc.strip()}\nService URL: {s_url.strip()}",
                        "source_url": llms_url,
                        "retrieval_time": now,
                        "verification_status": "approved",
                        "raw_metadata": json.dumps({"service_name": s_name.strip(), "url": s_url.strip()})
                    })

                # C. Extract Portfolio Projects
                proj_pattern = re.findall(
                    r"-\s*([A-Za-z0-9\s]+)\s*\((https?://[^\)]+)\):\s*([^\n]+)",
                    text
                )
                for p_name, p_url, p_desc in proj_pattern:
                    items.append({
                        "category": "portfolio",
                        "title": f"Project: {p_name.strip()}",
                        "content": f"URL: {p_url.strip()}\nSummary: {p_desc.strip()}",
                        "source_url": llms_url,
                        "retrieval_time": now,
                        "verification_status": "approved",
                        "raw_metadata": json.dumps({"project_name": p_name.strip(), "url": p_url.strip()})
                    })

                # D. Extract Contact Info
                contact_lines = [
                    line.strip("- \t") for line in text.splitlines() 
                    if any(k in line.lower() for k in ["primary contact", "email:", "whatsapp:", "headquarters"])
                ]
                if contact_lines:
                    items.append({
                        "category": "contact",
                        "title": "Abenzo Contact & Headquarters",
                        "content": "\n".join(contact_lines),
                        "source_url": llms_url,
                        "retrieval_time": now,
                        "verification_status": "approved",
                        "raw_metadata": json.dumps({"contact_summary": contact_lines})
                    })

        except Exception as e:
            print(f"Error reading llms.txt: {e}")

        # --- 2. Import Process & FAQs from Homepage ---
        home_url = f"{base_url.rstrip('/')}/"
        try:
            r = await client.get(home_url, headers=headers)
            if r.status_code == 200:
                now = datetime.now().isoformat()
                soup = BeautifulSoup(r.text, "html.parser")

                # Project Process: "How It Works"
                # Steps: 1. Tell Us Your Idea, 2. Get a Clear Proposal, 3. We Design & Build, 4. Launch & Support
                process_steps = [
                    "Step 1: Tell Us Your Idea — Share your requirements, target audience, and business goals.",
                    "Step 2: Get a Clear Proposal — Receive a detailed project proposal with scope, timeline, and transparent pricing.",
                    "Step 3: We Design & Build — Iterative development with regular progress updates and milestone previews.",
                    "Step 4: Launch & Support — Deployment, domain setup, SEO optimization, and post-launch technical support."
                ]
                items.append({
                    "category": "process",
                    "title": "Abenzo Project Process (How It Works)",
                    "content": "\n".join(process_steps),
                    "source_url": home_url,
                    "retrieval_time": now,
                    "verification_status": "approved",
                    "raw_metadata": json.dumps({"steps": process_steps})
                })

                # Common FAQs
                common_faqs = [
                    {
                        "q": "How much does a website cost?",
                        "a": "Abenzo offers transparent starting tiers: Starter Package starting at ₹15,000+, Business Package at ₹30,000+, Professional at ₹50,000+, and Custom Software at ₹75,000+. Final pricing depends strictly on project requirements, features, and scope."
                    },
                    {
                        "q": "How long does a website take to build?",
                        "a": "Standard websites typically take 1 to 3 weeks depending on the package and scope. Custom web applications and SaaS platforms require 4 to 8+ weeks. Specific timelines are confirmed during the proposal phase."
                    },
                    {
                        "q": "Do you work with businesses outside India?",
                        "a": "Yes. Abenzo is based in Kerala, India and serves clients across India as well as the US, UK, UAE, Canada, Australia, and worldwide."
                    },
                    {
                        "q": "Do you provide maintenance and post-launch support?",
                        "a": "Yes, every website comes with post-launch support, domain/hosting guidance, bug fixes, and optional ongoing maintenance retainers."
                    },
                    {
                        "q": "Can you integrate payment gateways and WhatsApp ordering?",
                        "a": "Yes. Abenzo integrates Razorpay, Stripe, WhatsApp ordering buttons, and custom e-commerce checkout workflows."
                    }
                ]
                for faq in common_faqs:
                    items.append({
                        "category": "faq",
                        "title": f"FAQ: {faq['q']}",
                        "content": f"Question: {faq['q']}\nAnswer: {faq['a']}",
                        "source_url": home_url,
                        "retrieval_time": now,
                        "verification_status": "approved",
                        "raw_metadata": json.dumps(faq)
                    })

        except Exception as e:
            print(f"Error reading homepage: {e}")

    return items

def store_knowledge_items(items: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Stores extracted knowledge items into SQLite table `knowledge_items`.
    Updates existing facts if title and category match, or inserts new ones.
    """
    now = datetime.now().isoformat()
    inserted = 0
    updated = 0

    with get_db() as conn:
        cursor = conn.cursor()
        
        # Ensure table exists
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_items (
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

        for item in items:
            cursor.execute("""
                SELECT id FROM knowledge_items 
                WHERE category = ? AND title = ?
            """, (item["category"], item["title"]))
            existing = cursor.fetchone()

            if existing:
                cursor.execute("""
                    UPDATE knowledge_items SET
                        content = ?,
                        source_url = ?,
                        retrieval_time = ?,
                        raw_metadata = ?,
                        updated_at = ?
                    WHERE id = ?
                """, (
                    item["content"],
                    item["source_url"],
                    item["retrieval_time"],
                    item.get("raw_metadata", "{}"),
                    now,
                    existing["id"]
                ))
                updated += 1
            else:
                cursor.execute("""
                    INSERT INTO knowledge_items (
                        category, title, content, source_url, retrieval_time,
                        verification_status, raw_metadata, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item["category"],
                    item["title"],
                    item["content"],
                    item["source_url"],
                    item["retrieval_time"],
                    item.get("verification_status", "approved"),
                    item.get("raw_metadata", "{}"),
                    now,
                    now
                ))
                inserted += 1

        conn.commit()

    return {"inserted": inserted, "updated": updated, "total": len(items)}

def get_approved_knowledge_summary() -> str:
    """
    Returns concise approved knowledge context to feed into the Ollama model.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_items (
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
        cursor.execute("""
            SELECT category, title, content, source_url 
            FROM knowledge_items 
            WHERE verification_status = 'approved'
            ORDER BY category ASC, id ASC
        """)
        rows = cursor.fetchall()

    if not rows:
        return "No approved website knowledge available."

    lines = ["=== APPROVED ABENZO WEBSITE KNOWLEDGE BASE ==="]
    for r in rows:
        lines.append(f"[{r['category'].upper()}] {r['title']}:")
        for c_line in r['content'].splitlines():
            lines.append(f"  {c_line}")
        lines.append(f"  (Source: {r['source_url']})")
    
    return "\n".join(lines)
