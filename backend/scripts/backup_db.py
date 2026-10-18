#!/usr/bin/env python3
"""
Abenzo AI - Safe Database Backup & Migration Export Tool
Preserves all records (knowledge_items, leads, conversations, conversation_events, app_settings)
without modifying or deleting the source database.
"""

import os
import sys
import json
import sqlite3
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "abenzo.db"
BACKUP_DIR = BASE_DIR / "backups"

def backup_database():
    if not DB_PATH.exists():
        print(f"[!] Database file not found at: {DB_PATH}")
        sys.exit(1)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 1. Native SQLite backup (.db file)
    sqlite_backup_file = BACKUP_DIR / f"abenzo_backup_{timestamp}.db"
    src_conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    dst_conn = sqlite3.connect(str(sqlite_backup_file))
    with dst_conn:
        src_conn.backup(dst_conn)
    dst_conn.close()
    src_conn.close()
    print(f"[✓] Created binary SQLite backup at: {sqlite_backup_file}")

    # 2. Structured JSON dump for migration / seeding
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    tables = ["leads", "conversations", "conversation_events", "app_settings", "knowledge_items"]
    export_data = {
        "exported_at": datetime.now().isoformat(),
        "source_db": str(DB_PATH),
        "tables": {}
    }

    print("\n--- Current Database Summary ---")
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        cursor.execute(f"SELECT * FROM {table}")
        rows = [dict(r) for r in cursor.fetchall()]
        export_data["tables"][table] = rows
        print(f"  • {table}: {count} records preserved")

    json_backup_file = BACKUP_DIR / f"abenzo_export_{timestamp}.json"
    latest_json_file = BACKUP_DIR / "latest_seed_backup.json"

    with open(json_backup_file, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)

    with open(latest_json_file, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)

    conn.close()
    print(f"[✓] Created portable JSON backup at: {json_backup_file}")
    print(f"[✓] Updated latest seed file at: {latest_json_file}")
    print("\nBackup complete. Zero records were modified or deleted.")

if __name__ == "__main__":
    backup_database()
