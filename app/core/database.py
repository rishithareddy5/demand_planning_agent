import os
import psycopg2
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv
import logging
from datetime import date

load_dotenv(override=False)

logger = logging.getLogger(__name__)

# ── Connection config ──────────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@postgres:5432/demand_planning"
)

POSTGRES_HOST     = os.getenv("POSTGRES_HOST", "127.0.0.1")
POSTGRES_PORT     = os.getenv("POSTGRES_PORT", "5433")
POSTGRES_DB       = os.getenv("POSTGRES_DB", "demand_planning")
POSTGRES_USER     = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")

# ── SQLAlchemy setup (unchanged from your original) ────────────────────────────
engine       = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base         = declarative_base()


def get_db():
    """FastAPI dependency — yields a SQLAlchemy session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_connection():
    """
    Raw psycopg2 connection — used by scripts and Temporal activities
    that need direct SQL without SQLAlchemy ORM overhead.
    """
    return psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD
    )


# ── NEW: confirmed_demands table helpers ───────────────────────────────────────
# These are called by Temporal's write_confirmed_qty_activity after
# validation passes. They write the final confirmed quantities +
# weekly breakdown + locked_demand flag to PostgreSQL.
# Metabase reads directly from these columns for the dashboard.

def ensure_confirmed_demands_table():
    """
    Create confirmed_demands table if it doesn't exist.
    Call once at startup from main.py lifespan or as a migration step.

    Columns mirror the architecture diagram exactly:
        confirmed_30d_qty  — total qty the distributor confirmed
        week1_qty .. week4_qty — split computed by demand_planning_service
        demand_status_locked   — True once DemandConfirmed event is emitted
        reply_latency_days     — days between EmailSent and ReplyReceived
        validation_status      — 'valid' | 'review'
        cycle_date             — which monthly cycle this belongs to
    """
    ddl = """
        CREATE TABLE IF NOT EXISTS confirmed_demands (
            id                   SERIAL PRIMARY KEY,
            distributor_id       VARCHAR(20)  NOT NULL,
            sku_id               VARCHAR(50)  NOT NULL,
            confirmed_30d_qty    INTEGER      NOT NULL DEFAULT 0,
            week1_qty            INTEGER      NOT NULL DEFAULT 0,
            week2_qty            INTEGER      NOT NULL DEFAULT 0,
            week3_qty            INTEGER      NOT NULL DEFAULT 0,
            week4_qty            INTEGER      NOT NULL DEFAULT 0,
            demand_status_locked BOOLEAN      NOT NULL DEFAULT FALSE,
            reply_latency_days   INTEGER,
            validation_status    VARCHAR(20)  NOT NULL DEFAULT 'valid',
            cycle_date           DATE         NOT NULL DEFAULT CURRENT_DATE,
            parsed_reply_id      INTEGER REFERENCES parsed_replies(id),
            created_at           TIMESTAMP    NOT NULL DEFAULT NOW(),
            updated_at           TIMESTAMP    NOT NULL DEFAULT NOW(),

            -- Prevent duplicate rows for same distributor+SKU in same cycle
            UNIQUE (distributor_id, sku_id, cycle_date)
        );

        -- Index for Metabase dashboard queries (filter by cycle_date, distributor)
        CREATE INDEX IF NOT EXISTS idx_confirmed_demands_distributor
            ON confirmed_demands (distributor_id, cycle_date);

        CREATE INDEX IF NOT EXISTS idx_confirmed_demands_cycle
            ON confirmed_demands (cycle_date);
    """
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(ddl)
        logger.info("[DB] confirmed_demands table ready")
    finally:
        conn.close()


def write_confirmed_qty(
    distributor_id: str,
    sku_id: str,
    confirmed_30d_qty: int,
    week1_qty: int,
    week2_qty: int,
    week3_qty: int,
    week4_qty: int,
    reply_latency_days: int | None,
    validation_status: str,
    parsed_reply_id: int | None,
    cycle_date: date | None = None,
) -> int:
    """
    Upsert one SKU row into confirmed_demands.

    Uses ON CONFLICT so re-running the Temporal activity (on retry)
    is safe — it will update instead of inserting a duplicate.

    Returns the row ID.

    Called by: Temporal write_confirmed_qty_activity (activities.py)
    """
    cycle_date = cycle_date or date.today()

    sql = """
        INSERT INTO confirmed_demands (
            distributor_id, sku_id,
            confirmed_30d_qty,
            week1_qty, week2_qty, week3_qty, week4_qty,
            demand_status_locked,
            reply_latency_days,
            validation_status,
            parsed_reply_id,
            cycle_date,
            updated_at
        ) VALUES (
            %(distributor_id)s, %(sku_id)s,
            %(confirmed_30d_qty)s,
            %(week1_qty)s, %(week2_qty)s, %(week3_qty)s, %(week4_qty)s,
            TRUE,
            %(reply_latency_days)s,
            %(validation_status)s,
            %(parsed_reply_id)s,
            %(cycle_date)s,
            NOW()
        )
        ON CONFLICT (distributor_id, sku_id, cycle_date)
        DO UPDATE SET
            confirmed_30d_qty    = EXCLUDED.confirmed_30d_qty,
            week1_qty            = EXCLUDED.week1_qty,
            week2_qty            = EXCLUDED.week2_qty,
            week3_qty            = EXCLUDED.week3_qty,
            week4_qty            = EXCLUDED.week4_qty,
            demand_status_locked = TRUE,
            reply_latency_days   = EXCLUDED.reply_latency_days,
            validation_status    = EXCLUDED.validation_status,
            updated_at           = NOW()
        RETURNING id;
    """

    params = {
        "distributor_id":    distributor_id,
        "sku_id":            sku_id,
        "confirmed_30d_qty": confirmed_30d_qty,
        "week1_qty":         week1_qty,
        "week2_qty":         week2_qty,
        "week3_qty":         week3_qty,
        "week4_qty":         week4_qty,
        "reply_latency_days": reply_latency_days,
        "validation_status": validation_status,
        "parsed_reply_id":   parsed_reply_id,
        "cycle_date":        cycle_date,
    }

    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                row_id = cur.fetchone()[0]
        logger.info(
            f"[DB] write_confirmed_qty: distributor={distributor_id} "
            f"sku={sku_id} qty={confirmed_30d_qty} row_id={row_id}"
        )
        return row_id
    finally:
        conn.close()


def get_confirmed_demands_for_distributor(distributor_id: str, cycle_date: date | None = None) -> list[dict]:
    """
    Fetch all confirmed SKU rows for a distributor in a given cycle.
    Used by Metabase queries and the demand_planning_service.

    Returns list of dicts with all columns.
    """
    cycle_date = cycle_date or date.today()

    sql = """
        SELECT
            id, distributor_id, sku_id,
            confirmed_30d_qty,
            week1_qty, week2_qty, week3_qty, week4_qty,
            demand_status_locked,
            reply_latency_days,
            validation_status,
            cycle_date,
            created_at
        FROM confirmed_demands
        WHERE distributor_id = %s
          AND cycle_date = %s
        ORDER BY sku_id;
    """

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (distributor_id, cycle_date))
            cols = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
            return [dict(zip(cols, row)) for row in rows]
    finally:
        conn.close()


def lock_demand_for_distributor(distributor_id: str, cycle_date: date | None = None):
    """
    Set demand_status_locked = TRUE for all SKUs of a distributor
    in the current cycle. Called after DemandConfirmed is emitted.
    """
    cycle_date = cycle_date or date.today()

    sql = """
        UPDATE confirmed_demands
        SET demand_status_locked = TRUE, updated_at = NOW()
        WHERE distributor_id = %s AND cycle_date = %s;
    """

    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, (distributor_id, cycle_date))
        logger.info(f"[DB] Demand locked for distributor={distributor_id} cycle={cycle_date}")
    finally:
        conn.close()