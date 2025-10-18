# db_config.py
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from pymongo import MongoClient, ASCENDING, UpdateOne
from pymongo.server_api import ServerApi
from datetime import datetime
import pandas as pd

load_dotenv()

# ---- Config & paths (relative to this file) ----
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEMA_SQL_PATH = os.getenv("DB_SETUP_SQL", os.path.join(BASE_DIR, "assets"))
INSERT_SQL_PATH = os.getenv("DB_INSERT_SQL", os.path.join(BASE_DIR, "assets"))
CSV_PATH       = os.getenv("DB_CSV_PATH", os.path.join(BASE_DIR, "assets"))
APP_LOCK_KEY   = int(os.getenv("DB_APP_LOCK_KEY", "742031"))

MONGO_DB_NAME = os.getenv("MONGO_DB_NAME")
MONGO_URI     = os.getenv("MONGO_URI")
REVIEWS_XLSX  = os.getenv("REVIEWS_XLSX", os.path.join(BASE_DIR, "assets"))
MONGO_COLL    = os.getenv("MONGO_COLLECTION")
MONGO_META    = os.getenv("MONGO_META_COLLECTION")

# ---- Single engine factory ----
_SQL_ENGINE = None
def get_sql_engine():
    """
    Return a SQLAlchemy engine for Postgres (psycopg2).
    Prefer a full DSN via SQL_DSN (works with Supabase pooler 6543).
    Falls back to parts if needed.
    """
    global _SQL_ENGINE
    if _SQL_ENGINE is not None:
        return _SQL_ENGINE

    dsn = (os.getenv("SQL_DSN") or "").strip()
    if dsn:
        if "sslmode=" not in dsn:
            dsn += ("&" if "?" in dsn else "?") + "sslmode=require"
        _SQL_ENGINE = create_engine(
            dsn,
            pool_pre_ping=True,
            pool_recycle=1800,
            pool_size=5,
            max_overflow=5,
            echo=os.getenv("SQL_ECHO", "false").lower() == "true",
        )
        return _SQL_ENGINE

    else:
        return _SQL_ENGINE

# Database initializer
# inside db_config.py
def init_sql_db():
    """
    Returns (success: bool, message: str)
    - success=True if initialized successfully or already up-to-date
    - success=False if setup failed
    """
    if os.getenv("DB_AUTO_MIGRATE", "true").lower() not in ("1", "true", "yes"):
        return (True, "Auto-migration disabled in .env")

    engine = get_sql_engine()
    read_sql = lambda p: open(p, "r", encoding="utf-8").read()
    table_exists = lambda conn, t: bool(conn.execute(text("""
        SELECT EXISTS (SELECT 1 FROM information_schema.tables
                       WHERE table_schema='public' AND table_name=:t)
    """), {"t": t}).scalar())
    table_has_rows = lambda conn, t: bool(conn.execute(text(f"SELECT EXISTS (SELECT 1 FROM {t} LIMIT 1);")).scalar())

    try:
        with engine.begin() as conn:
            locked = conn.exec_driver_sql(f"SELECT pg_try_advisory_lock({APP_LOCK_KEY});").scalar()
            if not locked:
                return (True, "Another process is initializing — skipped safely.")

            conn.exec_driver_sql("""
                CREATE TABLE IF NOT EXISTS app_meta (
                  key text PRIMARY KEY,
                  value text NOT NULL,
                  updated_at timestamptz NOT NULL DEFAULT now()
                );
            """)
            version = conn.execute(text("SELECT value FROM app_meta WHERE key='schema_version';")).first()
            if version:
                conn.exec_driver_sql(f"SELECT pg_advisory_unlock({APP_LOCK_KEY});")
                return (True, "SQL already initialized.")

            # Run schema setup
            if os.path.isfile(SCHEMA_SQL_PATH):
                conn.exec_driver_sql(read_sql(SCHEMA_SQL_PATH))

        # Copy CSV (if applicable)
        if os.path.isfile(CSV_PATH):
            with engine.begin() as conn2:
                if table_exists(conn2, "staging_hdb") and not table_has_rows(conn2, "staging_hdb"):
                    raw = engine.raw_connection()
                    try:
                        with raw.cursor() as cur, open(CSV_PATH, "r", encoding="utf-8") as f:
                            cur.copy_expert("COPY staging_hdb FROM STDIN WITH CSV HEADER", f)
                        raw.commit()
                    finally:
                        raw.close()

        # Insert transformations
        with engine.begin() as conn3:
            if os.path.isfile(INSERT_SQL_PATH):
                if table_exists(conn3, "transactions") and not table_has_rows(conn3, "transactions"):
                    conn3.exec_driver_sql(read_sql(INSERT_SQL_PATH))
            conn3.execute(text("""
                INSERT INTO app_meta (key, value)
                VALUES ('schema_version','1')
                ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=now();
            """))
            conn3.exec_driver_sql(f"SELECT pg_advisory_unlock({APP_LOCK_KEY});")

        return (True, "Database successfully initialized and ready.")
    except Exception as e:
        return (False, f"Database initialization failed: {e}")



# -------------------------------
# NoSQL DB (MongoDB)
# -------------------------------
MONGO_CLIENT = None

def get_mongo_client():
    global MONGO_CLIENT
    if MONGO_CLIENT is None:
        if MONGO_URI.startswith("mongodb+srv://"):
            MONGO_CLIENT = MongoClient(MONGO_URI, server_api=ServerApi("1"))
        else:
            MONGO_CLIENT = MongoClient(MONGO_URI)
    return MONGO_CLIENT

def init_mongo():
    if os.getenv("MONGO_AUTO_LOAD", "true").lower() not in ("1", "true", "yes"):
        return True, "Mongo auto-load disabled in .env"

    try:
        client = get_mongo_client()
        db = client[MONGO_DB_NAME]
        db.command("ping")  # connectivity check

        # first-run marker (separate from SQL side; lives in Mongo)
        meta = db[MONGO_META]
        if meta.find_one({"_id": "mongo_schema_version"}):
            return True, "Mongo already initialized."

        coll = db[MONGO_COLL]

        # --- import Excel (idempotent upserts) ---
        if not os.path.isfile(REVIEWS_XLSX):
            # Still set marker so we don’t loop forever; you can delete it if you want to retry later.
            meta.update_one(
                {"_id": "mongo_schema_version"},
                {"$set": {"value": "1", "note": "no file", "updated_at": datetime.utcnow()}},
                upsert=True,
            )
            return True, f"Mongo init: reviews file not found ({REVIEWS_XLSX}); marked as initialized."

        df = pd.read_excel(REVIEWS_XLSX)

        # map headers → app schema (adjust if your sheet differs)
        rename_map = {
            "ID": "review_id",
            "username": "user",
            "review text": "review_text",
            "created on": "created_at",
        }
        df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)

        if "town" not in df.columns or "rating" not in df.columns:
            raise RuntimeError("Excel must contain at least 'town' and 'rating' columns.")

        # normalize
        df["town"] = df["town"].astype(str).str.strip().str.upper()
        df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
        if "created_at" in df.columns:
            df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")

        # bulk upserts (prefer unique review_id, else composite)
        ops = []
        for r in df.to_dict("records"):
            if pd.notna(r.get("review_id")):
                filt = {"review_id": int(r["review_id"])}
            else:
                filt = {
                    "town": r.get("town"),
                    "user": r.get("user"),
                    "created_at": r.get("created_at"),
                    "review_text": r.get("review_text"),
                }
            doc = {k: v for k, v in r.items() if pd.notna(v)}
            ops.append(UpdateOne(filt, {"$set": doc}, upsert=True))

        upserted = modified = 0
        if ops:
            res = coll.bulk_write(ops, ordered=False)
            upserted, modified = res.upserted_count, res.modified_count

        # indexes (idempotent)
        try:
            coll.create_index([("review_id", ASCENDING)], unique=True, sparse=True)
        except Exception:
            pass
        coll.create_index([("town", ASCENDING)])
        coll.create_index([("created_at", ASCENDING)])

        # set first-run marker
        meta.update_one(
            {"_id": "mongo_schema_version"},
            {"$set": {"value": "1", "updated_at": datetime.utcnow()}},
            upsert=True,
        )

        return True, f"Mongo initialized. Upserted: {upserted}, Modified: {modified}."
    except Exception as e:
        return False, f"Mongo initialization failed: {e}"
