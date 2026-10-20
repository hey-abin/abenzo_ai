import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager
from backend.app.config import settings

logger = logging.getLogger("abenzo.database")


# ---------------------------------------------------------------------------
# Helpers for dual SQLite / PostgreSQL support
# ---------------------------------------------------------------------------

def _is_postgres() -> bool:
    """Check if PostgreSQL (Neon) is configured via DATABASE_URL."""
    return settings.is_postgres


def _pg_connection():
    """Create a psycopg PostgreSQL connection with connection and statement timeouts."""
    import psycopg
    logger.info("[Database] Connecting to PostgreSQL (Neon)...")
    conn = psycopg.connect(
        settings.DATABASE_URL,
        autocommit=False,
        connect_timeout=10,
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '15s'; SET lock_timeout = '5s';")
        conn.commit()
    except Exception as e:
        logger.warning("[Database] Could not set session timeouts on PostgreSQL connection: %s", e)
    logger.info("[Database] Connected to PostgreSQL successfully.")
    return conn


def _sqlite_connection(db_path: str = None):
    """Create a SQLite connection with WAL mode and foreign keys."""
    path = db_path or settings.DB_PATH
    conn = sqlite3.connect(path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


class PgRowAdapter:
    """Wraps a psycopg cursor row (tuple) to behave like sqlite3.Row with dict() support."""
    __slots__ = ("_keys", "_values")

    def __init__(self, keys, values):
        self._keys = keys
        self._values = values

    def __getitem__(self, key):
        if isinstance(key, str):
            try:
                idx = self._keys.index(key)
                return self._values[idx]
            except ValueError:
                raise KeyError(key)
        return self._values[key]

    def keys(self):
        return self._keys

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)


class PgCursorWrapper:
    """
    Wraps psycopg cursor to return PgRowAdapter rows (dict-like, like sqlite3.Row).
    Auto-converts SQLite-style '?' placeholders to PostgreSQL '%s' so existing
    router code works unchanged on both database engines.
    """

    # SQLite SQL patterns that need PostgreSQL equivalents
    _PRAGMA_PATTERN = None  # Lazily compiled

    def __init__(self, cursor):
        self._cursor = cursor
        self._last_insert_id = None

    @staticmethod
    def _convert_sql(sql):
        """Convert SQLite SQL dialect to PostgreSQL."""
        import re
        # Skip PRAGMA statements (no-op on PostgreSQL)
        if sql.strip().upper().startswith("PRAGMA"):
            return None
        # Convert ? placeholders to %s
        converted = sql.replace("?", "%s")
        # Convert datetime('now') to NOW()
        converted = re.sub(r"datetime\(['\"]now['\"]\)", "NOW()", converted, flags=re.IGNORECASE)
        # Convert INTEGER PRIMARY KEY AUTOINCREMENT to SERIAL PRIMARY KEY
        converted = re.sub(
            r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT",
            "SERIAL PRIMARY KEY",
            converted,
            flags=re.IGNORECASE
        )
        return converted

    def execute(self, sql, params=None):
        converted = self._convert_sql(sql)
        if converted is None:
            # PRAGMA or no-op: return self with empty result
            return self
        # For INSERT statements, append RETURNING id to capture lastrowid (except tables without id column like app_settings)
        upper = converted.strip().upper()
        if upper.startswith("INSERT") and "RETURNING" not in upper and "APP_SETTINGS" not in upper:
            converted = converted.rstrip().rstrip(";") + " RETURNING id"
            self._cursor.execute(converted, params)
            row = self._cursor.fetchone()
            if row:
                self._last_insert_id = row[0]
        else:
            self._cursor.execute(converted, params)
        return self

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        if self._cursor.description:
            keys = [desc[0] for desc in self._cursor.description]
            return PgRowAdapter(keys, row)
        return row

    def fetchall(self):
        rows = self._cursor.fetchall()
        if self._cursor.description:
            keys = [desc[0] for desc in self._cursor.description]
            return [PgRowAdapter(keys, row) for row in rows]
        return rows

    @property
    def lastrowid(self):
        return self._last_insert_id

    @property
    def description(self):
        return self._cursor.description


class PgConnectionWrapper:
    """Wraps psycopg connection to provide cursor() returning PgCursorWrapper."""

    def __init__(self, conn):
        self._conn = conn
        self._last_insert_id = None

    def cursor(self):
        return PgCursorWrapper(self._conn.cursor())

    def execute(self, sql, params=None):
        cur = self._conn.cursor()
        cur.execute(sql, params)
        return PgCursorWrapper(cur)

    def commit(self):
        if not getattr(self._conn, "closed", False):
            self._conn.commit()

    def rollback(self):
        try:
            if not getattr(self._conn, "closed", False):
                self._conn.rollback()
        except Exception:
            pass

    def close(self):
        try:
            if not getattr(self._conn, "closed", False):
                self._conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Public API: get_db_connection, get_db, init_db
# ---------------------------------------------------------------------------

def get_db_connection(db_path: str = None):
    """
    Returns a database connection.
    - If DATABASE_URL is set: returns PgConnectionWrapper (PostgreSQL/Neon)
    - Otherwise: returns sqlite3.Connection (local development)
    The db_path parameter is only used for SQLite (e.g., testing).
    """
    if _is_postgres() and db_path is None:
        return PgConnectionWrapper(_pg_connection())
    return _sqlite_connection(db_path)


@contextmanager
def get_db(db_path: str = None):
    """Context manager for database connections with auto-commit/rollback."""
    conn = get_db_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            # Ensure connection termination or rollback failure does not mask the original exception
            pass
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# SQL abstraction: paramstyle and schema differences
# ---------------------------------------------------------------------------

def _ph(count=1):
    """Return placeholder(s) for SQL queries (works with SQLite, auto-converted to %s by PgCursorWrapper on PostgreSQL)."""
    return ", ".join(["?"] * count)


def _serial_pk():
    """Return the PRIMARY KEY definition for auto-increment IDs."""
    if _is_postgres():
        return "id SERIAL PRIMARY KEY"
    return "id INTEGER PRIMARY KEY AUTOINCREMENT"


def _now_default():
    """Return the SQL expression for 'now' in INSERT statements."""
    if _is_postgres():
        return "NOW()"
    return "datetime('now')"


# ---------------------------------------------------------------------------
# Schema initialization (works for both SQLite and PostgreSQL)
# ---------------------------------------------------------------------------

def init_db(db_path: str = None):
    """
    Initialize all five tables. Safe to call repeatedly (CREATE IF NOT EXISTS).
    On PostgreSQL, backward-compatible column migrations use ADD COLUMN IF NOT EXISTS.
    On SQLite, PRAGMA table_info is used for migration detection.
    """
    using_pg = _is_postgres() and db_path is None
    logger.info("[init_db] Starting database schema initialization (engine=%s)...", "postgresql" if using_pg else "sqlite")

    with get_db(db_path) as conn:
        cursor = conn.cursor()

        # 1. Leads table
        cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS leads (
            {_serial_pk()},
            business_name TEXT NOT NULL,
            industry TEXT DEFAULT '',
            state TEXT DEFAULT '',
            city TEXT DEFAULT '',
            source_url TEXT DEFAULT '',
            instagram_url TEXT DEFAULT '',
            instagram_handle TEXT DEFAULT '',
            website_url TEXT DEFAULT '',
            website_status TEXT DEFAULT 'uncertain',
            evidence_json TEXT DEFAULT '{json.dumps({})}',
            business_summary TEXT DEFAULT '',
            lead_score INTEGER DEFAULT 0,
            confidence TEXT DEFAULT 'uncertain',
            opportunity TEXT DEFAULT '',
            recommended_service TEXT DEFAULT '',
            suggested_service TEXT DEFAULT '',
            observed_problems TEXT DEFAULT '',
            score_breakdown_json TEXT DEFAULT '{{}}',
            personalized_dm TEXT DEFAULT '',
            reasoning_summary TEXT DEFAULT '',
            next_best_action TEXT DEFAULT '',
            contact_name TEXT DEFAULT '',
            public_phone TEXT DEFAULT '',
            public_email TEXT DEFAULT '',
            project_timeline TEXT DEFAULT '',
            budget TEXT DEFAULT '',
            consent_source TEXT DEFAULT '',
            follow_up_date TEXT DEFAULT '',
            outreach_action_at TEXT DEFAULT '',
            conversation_id INTEGER DEFAULT NULL,
            outreach_status TEXT DEFAULT 'new',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """)

        # 2. Conversations table
        cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS conversations (
            {_serial_pk()},
            platform TEXT DEFAULT 'manual',
            external_thread_id TEXT,
            contact_display_name TEXT DEFAULT '',
            lead_id INTEGER,
            last_message_at TEXT,
            status TEXT DEFAULT 'active',
            needs_human INTEGER DEFAULT 1,
            lead_temperature TEXT DEFAULT 'early',
            notes TEXT DEFAULT '',
            recipient_id TEXT DEFAULT '',
            conversation_summary TEXT DEFAULT '',
            lead_context_json TEXT DEFAULT '{{}}',
            conversion_stage TEXT DEFAULT 'lead',
            auto_reply_paused INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE SET NULL
        );
        """)

        # 3. Conversation Events table
        cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS conversation_events (
            {_serial_pk()},
            conversation_id INTEGER NOT NULL,
            external_event_id TEXT UNIQUE,
            event_type TEXT DEFAULT 'dm',
            direction TEXT DEFAULT 'inbound',
            message_text TEXT NOT NULL,
            ai_draft TEXT DEFAULT '',
            approved_text TEXT DEFAULT '',
            delivery_status TEXT DEFAULT 'received',
            meta_message_id TEXT DEFAULT '',
            error_details TEXT DEFAULT '',
            sent_at TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        );
        """)

        # 4. Settings table
        cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """)

        # 5. Knowledge Base table
        cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS knowledge_items (
            {_serial_pk()},
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            source_url TEXT NOT NULL,
            retrieval_time TEXT NOT NULL,
            verification_status TEXT DEFAULT 'approved',
            raw_metadata TEXT DEFAULT '{json.dumps({})}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """)

        # 6. Autonomous Campaigns table
        cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS campaigns (
            {_serial_pk()},
            status TEXT DEFAULT 'running',
            stage TEXT DEFAULT 'checking_apis',
            current_step_text TEXT DEFAULT '',
            selected_hashtags_json TEXT DEFAULT '[]',
            meta_status_json TEXT DEFAULT '{{}}',
            discovered_posts_count INTEGER DEFAULT 0,
            unique_profiles_count INTEGER DEFAULT 0,
            qualified_prospects_count INTEGER DEFAULT 0,
            drafts_generated_count INTEGER DEFAULT 0,
            duplicates_count INTEGER DEFAULT 0,
            rejected_count INTEGER DEFAULT 0,
            provider_failures_json TEXT DEFAULT '[]',
            results_summary_json TEXT DEFAULT '[]',
            error_message TEXT DEFAULT '',
            started_at TEXT NOT NULL,
            completed_at TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """)

        # 7. Researched Hashtags table
        cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS prospecting_hashtags (
            {_serial_pk()},
            hashtag TEXT UNIQUE NOT NULL,
            rationale TEXT DEFAULT '',
            service_fit TEXT DEFAULT '',
            times_used INTEGER DEFAULT 0,
            last_used_at TEXT DEFAULT '',
            prospects_found INTEGER DEFAULT 0,
            qualified_found INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """)

        logger.info("[init_db] Core tables verified.")

        # Backward-compatible migrations
        if using_pg:
            # Query existing columns first to avoid unnecessary ALTER TABLE and ACCESS EXCLUSIVE locks
            cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'leads'")
            lead_cols = {row[0] for row in cursor.fetchall()}
            for col, col_def in (
                ("city", "TEXT DEFAULT ''"),
                ("instagram_handle", "TEXT DEFAULT ''"),
                ("suggested_service", "TEXT DEFAULT ''"),
                ("observed_problems", "TEXT DEFAULT ''"),
                ("score_breakdown_json", "TEXT DEFAULT '{}'"),
                ("contact_name", "TEXT DEFAULT ''"),
                ("public_phone", "TEXT DEFAULT ''"),
                ("public_email", "TEXT DEFAULT ''"),
                ("project_timeline", "TEXT DEFAULT ''"),
                ("budget", "TEXT DEFAULT ''"),
                ("consent_source", "TEXT DEFAULT ''"),
                ("follow_up_date", "TEXT DEFAULT ''"),
                ("outreach_action_at", "TEXT DEFAULT ''"),
                ("conversation_id", "INTEGER DEFAULT NULL"),
                ("source_media_id", "TEXT DEFAULT ''"),
                ("source_media_url", "TEXT DEFAULT ''"),
                ("source_caption", "TEXT DEFAULT ''"),
                ("discovery_hashtag", "TEXT DEFAULT ''"),
                ("campaign_id", "INTEGER DEFAULT NULL"),
            ):
                if col not in lead_cols:
                    cursor.execute(f"ALTER TABLE leads ADD COLUMN {col} {col_def}")

            cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'conversations'")
            conv_cols = {row[0] for row in cursor.fetchall()}
            for col, col_def in (
                ("recipient_id", "TEXT DEFAULT ''"),
                ("conversation_summary", "TEXT DEFAULT ''"),
                ("lead_context_json", "TEXT DEFAULT '{}'"),
                ("conversion_stage", "TEXT DEFAULT 'lead'"),
                ("auto_reply_paused", "INTEGER DEFAULT 0"),
            ):
                if col not in conv_cols:
                    cursor.execute(f"ALTER TABLE conversations ADD COLUMN {col} {col_def}")

            cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'conversation_events'")
            event_cols = {row[0] for row in cursor.fetchall()}
            for col in ("meta_message_id", "error_details", "sent_at"):
                if col not in event_cols:
                    cursor.execute(f"ALTER TABLE conversation_events ADD COLUMN {col} TEXT DEFAULT ''")

            # Synchronize serial sequences with current MAX(id) to avoid duplicate key violations
            for tbl in ("leads", "conversations", "conversation_events", "knowledge_items", "campaigns", "prospecting_hashtags"):
                try:
                    cursor.execute(f"""
                        SELECT setval(
                            pg_get_serial_sequence('{tbl}', 'id'),
                            COALESCE((SELECT MAX(id) FROM {tbl}), 1),
                            (SELECT MAX(id) FROM {tbl}) IS NOT NULL
                        );
                    """)
                except Exception:
                    pass
            logger.info("[init_db] PostgreSQL migrations and sequences synchronized.")
        else:
            # SQLite uses PRAGMA table_info for migration detection
            cursor.execute("PRAGMA table_info(leads)")
            lead_cols = [row[1] for row in cursor.fetchall()]
            for col, col_def in (
                ("city", "TEXT DEFAULT ''"),
                ("instagram_handle", "TEXT DEFAULT ''"),
                ("suggested_service", "TEXT DEFAULT ''"),
                ("observed_problems", "TEXT DEFAULT ''"),
                ("score_breakdown_json", "TEXT DEFAULT '{}'"),
                ("contact_name", "TEXT DEFAULT ''"),
                ("public_phone", "TEXT DEFAULT ''"),
                ("public_email", "TEXT DEFAULT ''"),
                ("project_timeline", "TEXT DEFAULT ''"),
                ("budget", "TEXT DEFAULT ''"),
                ("consent_source", "TEXT DEFAULT ''"),
                ("follow_up_date", "TEXT DEFAULT ''"),
                ("outreach_action_at", "TEXT DEFAULT ''"),
                ("conversation_id", "INTEGER DEFAULT NULL"),
                ("source_media_id", "TEXT DEFAULT ''"),
                ("source_media_url", "TEXT DEFAULT ''"),
                ("source_caption", "TEXT DEFAULT ''"),
                ("discovery_hashtag", "TEXT DEFAULT ''"),
                ("campaign_id", "INTEGER DEFAULT NULL"),
            ):
                if col not in lead_cols:
                    cursor.execute(f"ALTER TABLE leads ADD COLUMN {col} {col_def}")

            cursor.execute("PRAGMA table_info(conversations)")
            conv_cols = [row[1] for row in cursor.fetchall()]
            for col, col_def in (
                ("recipient_id", "TEXT DEFAULT ''"),
                ("conversation_summary", "TEXT DEFAULT ''"),
                ("lead_context_json", "TEXT DEFAULT '{}'"),
                ("conversion_stage", "TEXT DEFAULT 'lead'"),
                ("auto_reply_paused", "INTEGER DEFAULT 0"),
            ):
                if col not in conv_cols:
                    cursor.execute(f"ALTER TABLE conversations ADD COLUMN {col} {col_def}")

            cursor.execute("PRAGMA table_info(conversation_events)")
            event_cols = [row[1] for row in cursor.fetchall()]
            if "meta_message_id" not in event_cols:
                cursor.execute("ALTER TABLE conversation_events ADD COLUMN meta_message_id TEXT DEFAULT ''")
            if "error_details" not in event_cols:
                cursor.execute("ALTER TABLE conversation_events ADD COLUMN error_details TEXT DEFAULT ''")
            if "sent_at" not in event_cols:
                cursor.execute("ALTER TABLE conversation_events ADD COLUMN sent_at TEXT DEFAULT ''")
            logger.info("[init_db] SQLite migrations verified.")

        # Insert initial default business profile if not present
        cursor.execute(f"SELECT value FROM app_settings WHERE key = {_ph()}", ("business_profile",))
        if not cursor.fetchone():
            default_profile = {
                "agency_name": "Abenzo",
                "tagline": "Web Development Agency serving businesses across India",
                "services": [
                    "Custom Website Development",
                    "E-commerce & WhatsApp Ordering Storefronts",
                    "Landing Page Design & Conversion Optimization",
                    "Website Redesign & Speed Optimization",
                    "SEO & Digital Presence Setup"
                ],
                "portfolio_urls": [
                    "https://abenzo.in/portfolio"
                ],
                "contact_email": "hello@abenzo.in",
                "contact_phone": "",
                "service_areas": "All Indian States & Tier 1/2/3 Cities",
                "approved_faq": [
                    {
                        "question": "What services does Abenzo provide?",
                        "answer": "Abenzo designs and develops high-performing websites, landing pages, custom web applications, and e-commerce storefronts for Indian businesses."
                    },
                    {
                        "question": "How can I see your portfolio?",
                        "answer": "You can view our recent web design and development projects at https://abenzo.in/portfolio."
                    },
                    {
                        "question": "How can I get a quote or book a call?",
                        "answer": "You can share your requirement with us or book a quick 15-minute discovery call at https://abenzo.in/contact."
                    }
                ],
                "starting_prices": "",
                "discovery_call_url": "https://abenzo.in/contact",
                "tone_guidelines": "Helpful, transparent, professional, evidence-backed. Never aggressive, never fabricate guarantees.",
                "allowed_claims": "Specialized in responsive web development, modern tech stacks, fast turnaround, and Indian business localization.",
                "auto_reply_faq_enabled": False
            }
            now_sql = _now_default()
            cursor.execute(
                f"INSERT INTO app_settings (key, value, updated_at) VALUES ({_ph(2)}, {now_sql})",
                ("business_profile", json.dumps(default_profile))
            )
            logger.info("[init_db] Default business profile inserted.")
        else:
            logger.info("[init_db] Business profile already present.")

        # Insert initial default automation settings if not present
        cursor.execute(f"SELECT value FROM app_settings WHERE key = {_ph()}", ("automation_settings",))
        if not cursor.fetchone():
            default_automation = {
                "auto_reply_enabled": True,
                "auto_reply_paused_global": False,
                "require_human_approval": False
            }
            now_sql = _now_default()
            cursor.execute(
                f"INSERT INTO app_settings (key, value, updated_at) VALUES ({_ph(2)}, {now_sql})",
                ("automation_settings", json.dumps(default_automation))
            )
            logger.info("[init_db] Default automation settings inserted.")
        else:
            logger.info("[init_db] Automation settings already present.")

        # Seed initial knowledge items idempotently if empty or missing
        seeded = seed_initial_knowledge(cursor)
        logger.info("[init_db] Knowledge base verified (%d new items added).", seeded)

        conn.commit()
        logger.info("[init_db] Database initialization committed successfully.")


def seed_initial_knowledge(cursor) -> int:
    """
    Seeds initial verified knowledge items from backend/app/data/knowledge_seed.json
    idempotently without overwriting existing records or user edits.
    Works with both SQLite (? params) and PostgreSQL (%s params).
    """
    seed_file = Path(__file__).resolve().parent / "data" / "knowledge_seed.json"
    if not seed_file.exists():
        return 0

    try:
        with open(seed_file, "r", encoding="utf-8") as f:
            items = json.load(f)
    except Exception:
        return 0

    ph = _ph

    # Batch check existing (title, category) in one query to avoid 20 sequential round-trips
    try:
        cursor.execute("SELECT title, category FROM knowledge_items")
        rows = cursor.fetchall()
        existing = set()
        for r in rows:
            if isinstance(r, (list, tuple)):
                existing.add((r[0], r[1]))
            elif hasattr(r, "__getitem__"):
                existing.add((r["title"], r["category"]))
    except Exception:
        existing = set()

    inserted_count = 0
    now = datetime.now().isoformat()
    for item in items:
        title = item.get("title", "").strip()
        category = item.get("category", "").strip()
        if not title or not category:
            continue

        if (title, category) in existing:
            continue  # Already exists, never duplicate or overwrite

        cursor.execute(f"""
            INSERT INTO knowledge_items (
                category, title, content, source_url, retrieval_time,
                verification_status, raw_metadata, created_at, updated_at
            ) VALUES ({ph(9)})
        """, (
            category,
            title,
            item.get("content", ""),
            item.get("source_url", ""),
            item.get("retrieval_time", now),
            item.get("verification_status", "approved"),
            item.get("raw_metadata", "{}"),
            now,
            now
        ))
        inserted_count += 1
        existing.add((title, category))

    return inserted_count
