from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from backend.app.database import get_db
from backend.app.services.knowledge_service import (
    fetch_and_extract_website_knowledge,
    store_knowledge_items,
    get_approved_knowledge_summary
)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

class KnowledgeItemCreate(BaseModel):
    category: str
    title: str
    content: str
    source_url: str = "Manual Entry"
    verification_status: str = "approved"

class KnowledgeItemUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    verification_status: Optional[str] = None

class KnowledgeItemResponse(BaseModel):
    id: int
    category: str
    title: str
    content: str
    source_url: str
    retrieval_time: str
    verification_status: str
    created_at: str
    updated_at: str

@router.get("", response_model=List[KnowledgeItemResponse])
def get_knowledge_items(
    category: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None
):
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

        query = "SELECT * FROM knowledge_items WHERE 1=1"
        params = []

        if category and category != "all":
            query += " AND category = ?"
            params.append(category.lower())
        if status and status != "all":
            query += " AND verification_status = ?"
            params.append(status)
        if search:
            query += " AND (LOWER(title) LIKE ? OR LOWER(content) LIKE ?)"
            params.append(f"%{search.lower().strip()}%")
            params.append(f"%{search.lower().strip()}%")

        query += " ORDER BY category ASC, id ASC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

@router.post("/import")
async def import_website_knowledge(site_url: str = "https://abenzo.vercel.app"):
    """
    Crawls public AI files (/llms.txt) and public pages from https://abenzo.vercel.app
    and extracts verified packages, starting prices, services, portfolio, and FAQs.
    """
    items = await fetch_and_extract_website_knowledge(base_url=site_url)
    if not items:
        raise HTTPException(status_code=502, detail="Failed to extract any knowledge from site.")
    
    result = store_knowledge_items(items)
    return {
        "status": "success",
        "site_url": site_url,
        "items_extracted": len(items),
        "inserted": result["inserted"],
        "updated": result["updated"]
    }

@router.patch("/{item_id}", response_model=KnowledgeItemResponse)
def update_knowledge_item(item_id: int, item_in: KnowledgeItemUpdate):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM knowledge_items WHERE id = ?", (item_id,))
        existing = cursor.fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Knowledge item not found")

        updates = []
        params = []
        data = item_in.model_dump(exclude_unset=True)

        for k, v in data.items():
            updates.append(f"{k} = ?")
            params.append(v)

        if updates:
            updates.append("updated_at = ?")
            params.append(datetime.now().isoformat())
            params.append(item_id)
            cursor.execute(f"UPDATE knowledge_items SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()

        cursor.execute("SELECT * FROM knowledge_items WHERE id = ?", (item_id,))
        return dict(cursor.fetchone())

@router.delete("/{item_id}")
def delete_knowledge_item(item_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM knowledge_items WHERE id = ?", (item_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Knowledge item not found")
        cursor.execute("DELETE FROM knowledge_items WHERE id = ?", (item_id,))
        conn.commit()
        return {"status": "success", "message": f"Fact #{item_id} removed"}

@router.post("", response_model=KnowledgeItemResponse)
def create_custom_knowledge_item(item_in: KnowledgeItemCreate):
    now = datetime.now().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO knowledge_items (
                category, title, content, source_url, retrieval_time,
                verification_status, raw_metadata, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, '{}', ?, ?)
        """, (
            item_in.category.lower(),
            item_in.title.strip(),
            item_in.content.strip(),
            item_in.source_url.strip(),
            now,
            item_in.verification_status,
            now,
            now
        ))
        conn.commit()
        item_id = cursor.lastrowid
        cursor.execute("SELECT * FROM knowledge_items WHERE id = ?", (item_id,))
        return dict(cursor.fetchone())
