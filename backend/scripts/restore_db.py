#!/usr/bin/env python3
"""
Abenzo AI - Safe Database Restore Tool
Restores all five tables (leads, conversations, conversation_events, app_settings, knowledge_items)
from a verified JSON backup into SQLite or PostgreSQL (Neon) without destructive data loss.
"""

import os
import sys
import json
import sqlite3
import argparse
from pathlib import Path

# Add project root to sys.path so backend modules can be imported
BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.config import settings
from backend.app.database import get_db, init_db

DEFAULT_BACKUP = BASE_DIR / "backups" / "latest_seed_backup.json"
DEFAULT_DB = BASE_DIR / "abenzo.db"


def restore_database(backup_path: Path, db_path: Path = None, database_url: str = None, dry_run: bool = False, overwrite_settings: bool = False):
    if not backup_path.exists():
        print(f"[!] Backup file not found at: {backup_path}")
        sys.exit(1)

    with open(backup_path, "r", encoding="utf-8") as f:
        backup_data = json.load(f)

    tables_data = backup_data.get("tables", {})
    if not tables_data:
        print("[!] No table data found in backup JSON.")
        sys.exit(1)

    if database_url:
        os.environ["DATABASE_URL"] = database_url
        settings.DATABASE_URL = database_url

    is_pg = settings.is_postgres
    target_desc = f"PostgreSQL ({settings.DATABASE_URL.split('@')[-1] if '@' in settings.DATABASE_URL else 'configured'})" if is_pg else f"SQLite ({db_path or settings.DB_PATH})"
    print(f"[*] Target Database: {target_desc}")
    print(f"[*] Source Backup JSON: {backup_path} (Exported at: {backup_data.get('exported_at', 'unknown')})")
    print(f"[*] Dry-run mode: {dry_run}\n")

    # Ensure schema exists prior to restore
    effective_db_path = str(db_path) if (db_path and not is_pg) else None
    init_db(effective_db_path)

    stats = {}

    with get_db(effective_db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = OFF;")

        # 1. Leads
        leads = tables_data.get("leads", [])
        leads_added = 0
        for lead in leads:
            lead_id = lead.get("id")
            cursor.execute(
                "SELECT id FROM leads WHERE id = ? OR (business_name = ? AND website_url = ?)", 
                (lead_id, lead.get("business_name"), lead.get("website_url"))
            )
            if not cursor.fetchone():
                leads_added += 1
                if not dry_run:
                    cols = [k for k in lead.keys()]
                    placeholders = ", ".join(["?"] * len(cols))
                    cursor.execute(f"INSERT INTO leads ({', '.join(cols)}) VALUES ({placeholders})", [lead[k] for k in cols])
        stats["leads"] = (leads_added, len(leads))

        # 2. Conversations
        convs = tables_data.get("conversations", [])
        convs_added = 0
        for conv in convs:
            conv_id = conv.get("id")
            cursor.execute("SELECT id FROM conversations WHERE id = ? OR external_thread_id = ?", (conv_id, conv.get("external_thread_id")))
            if not cursor.fetchone():
                convs_added += 1
                if not dry_run:
                    cols = [k for k in conv.keys()]
                    placeholders = ", ".join(["?"] * len(cols))
                    cursor.execute(f"INSERT INTO conversations ({', '.join(cols)}) VALUES ({placeholders})", [conv[k] for k in cols])
        stats["conversations"] = (convs_added, len(convs))

        # 3. Conversation Events
        events = tables_data.get("conversation_events", [])
        events_added = 0
        for event in events:
            event_id = event.get("id")
            ext_id = event.get("external_event_id")
            cursor.execute("SELECT id FROM conversation_events WHERE id = ? OR external_event_id = ?", (event_id, ext_id))
            if not cursor.fetchone():
                events_added += 1
                if not dry_run:
                    cols = [k for k in event.keys()]
                    placeholders = ", ".join(["?"] * len(cols))
                    cursor.execute(f"INSERT INTO conversation_events ({', '.join(cols)}) VALUES ({placeholders})", [event[k] for k in cols])
        stats["conversation_events"] = (events_added, len(events))

        # 4. App Settings
        app_settings = tables_data.get("app_settings", [])
        settings_updated = 0
        for s in app_settings:
            key = s.get("key")
            cursor.execute("SELECT key FROM app_settings WHERE key = ?", (key,))
            exists = cursor.fetchone()
            if not exists:
                settings_updated += 1
                if not dry_run:
                    cursor.execute(
                        "INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)", 
                        (key, s.get("value"), s.get("updated_at"))
                    )
            elif overwrite_settings:
                settings_updated += 1
                if not dry_run:
                    cursor.execute(
                        "UPDATE app_settings SET value = ?, updated_at = ? WHERE key = ?",
                        (s.get("value"), s.get("updated_at"), key)
                    )
        stats["app_settings"] = (settings_updated, len(app_settings))

        # 5. Knowledge Items
        knowledge = tables_data.get("knowledge_items", [])
        knowledge_added = 0
        for k in knowledge:
            k_id = k.get("id")
            title = k.get("title")
            category = k.get("category")
            cursor.execute("SELECT id FROM knowledge_items WHERE id = ? OR (title = ? AND category = ?)", (k_id, title, category))
            if not cursor.fetchone():
                knowledge_added += 1
                if not dry_run:
                    cols = [col for col in k.keys()]
                    placeholders = ", ".join(["?"] * len(cols))
                    cursor.execute(f"INSERT INTO knowledge_items ({', '.join(cols)}) VALUES ({placeholders})", [k[col] for col in cols])
        stats["knowledge_items"] = (knowledge_added, len(knowledge))

        cursor.execute("PRAGMA foreign_keys = ON;")

    print("--- Restoration Summary ---")
    for table, (added, total) in stats.items():
        mode = "Restored" if not dry_run else "Would restore"
        print(f"  • {table}: {mode} {added} new record(s) out of {total} in backup")

    if dry_run:
        print("\n[!] Dry run complete. No database changes were made.")
    else:
        print(f"\n[✓] Restoration complete. Target {target_desc} is up to date.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Restore Abenzo database from JSON backup.")
    parser.add_argument("--backup", type=str, default=str(DEFAULT_BACKUP), help="Path to backup JSON file")
    parser.add_argument("--db", type=str, default=str(DEFAULT_DB), help="Target SQLite DB path")
    parser.add_argument("--database-url", type=str, default=None, help="PostgreSQL connection string (overrides --db)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate restoration without writing changes")
    parser.add_argument("--overwrite-settings", action="store_true", help="Overwrite existing app_settings with backup values")
    args = parser.parse_args()

    restore_database(
        Path(args.backup), 
        Path(args.db), 
        database_url=args.database_url,
        dry_run=args.dry_run, 
        overwrite_settings=args.overwrite_settings
    )
