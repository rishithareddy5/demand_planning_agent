"""
db/postgres/seed_recommended_products.py

Creates the recommended_products table and seeds it from:
    sample_data/30_Recommended_New_Products.xlsx
    Sheet: "3. Recommendation Mapping"

This is what sku_recommendation_service.py queries to get the
Excel-sourced recommendations (the second half of the combined list).

Run once before starting the application:
    python db/postgres/seed_recommended_products.py
"""

import os
import sys
import pandas as pd
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# ── DB connection ──────────────────────────────────────────────────────────────

def get_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", 5433)),
        dbname=os.getenv("POSTGRES_DB", "demand_planning"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
    )


# ── Create table ───────────────────────────────────────────────────────────────

def create_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS recommended_products (
            id              SERIAL PRIMARY KEY,
            distributor_id  VARCHAR(20)  NOT NULL,
            product_name    TEXT         NOT NULL,
            reason          TEXT,
            priority_rank   INTEGER      NOT NULL DEFAULT 1,
            created_at      TIMESTAMP    NOT NULL DEFAULT NOW()
        );
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_recommended_products_distributor
            ON recommended_products (distributor_id, priority_rank);
    """)

    print("✓ Table 'recommended_products' ready")


# ── Parse Excel ────────────────────────────────────────────────────────────────

def _extract_distributor_id(raw_value):
    if pd.notna(raw_value) and str(raw_value).strip():
        return str(raw_value).strip().split()[0]
    return None


def _is_valid_product(product_name: str):
    if not product_name or product_name.lower() == "nan":
        return False

    return product_name.lower() not in (
        "recommended sku",
        "product name",
        "sku name",
    )


def _safe_str(value):
    return str(value).strip() if pd.notna(value) else ""


def _safe_rank(value):
    return int(value) if pd.notna(value) else 99


def load_from_excel(file_path: str):
    df = pd.read_excel(file_path, sheet_name="3. Recommendation Mapping", header=None)

    df = df.iloc[3:].reset_index(drop=True)
    df.columns = ["distributor_raw", "rank", "product_name", "reason"]

    records = []
    current_distributor_id = None

    for _, row in df.iterrows():

        # Extract distributor if present
        extracted_id = _extract_distributor_id(row["distributor_raw"])
        if extracted_id:
            current_distributor_id = extracted_id

        if not current_distributor_id:
            continue

        product_name = _safe_str(row["product_name"])
        if not _is_valid_product(product_name):
            continue

        rank = _safe_rank(row["rank"])
        reason = _safe_str(row["reason"])

        records.append({
            "distributor_id": current_distributor_id,
            "product_name": product_name,
            "reason": reason,
            "priority_rank": rank,
        })

    return records


# ── Seed ───────────────────────────────────────────────────────────────────────

def seed(records, cur):
    # Clear existing rows first so re-running is safe
    cur.execute("DELETE FROM recommended_products;")
    print("Cleared existing rows")

    for rec in records:
        cur.execute("""
            INSERT INTO recommended_products (distributor_id, product_name, reason, priority_rank)
            VALUES (%s, %s, %s, %s);
        """, (
            rec["distributor_id"],
            rec["product_name"],
            rec["reason"],
            rec["priority_rank"],
        ))

    print(f"✓ Inserted {len(records)} recommended product rows")


# ── Verify ─────────────────────────────────────────────────────────────────────

def verify(cur):
    cur.execute("""
        SELECT distributor_id, COUNT(*) as count
        FROM recommended_products
        GROUP BY distributor_id
        ORDER BY distributor_id;
    """)
    rows = cur.fetchall()
    print("\n── Verification ──────────────────────────────")
    for dist_id, count in rows:
        print(f"  {dist_id}: {count} recommended products")

    cur.execute("""
        SELECT distributor_id, product_name, priority_rank
        FROM recommended_products
        ORDER BY distributor_id, priority_rank
        LIMIT 15;
    """)
    sample = cur.fetchall()
    print("\n── Sample rows (first 15) ────────────────────")
    for dist_id, product_name, rank in sample:
        print(f"  [{dist_id}] #{rank}  {product_name}")
    print("──────────────────────────────────────────────")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    EXCEL_FILE = "sample_data/30_Recommended_New_Products.xlsx"

    print("=" * 55)
    print("  Seeding recommended_products table")
    print("=" * 55)

    # Check file exists
    if not os.path.exists(EXCEL_FILE):
        print(f"✗ File not found: {EXCEL_FILE}")
        print("  Make sure you run this from the project root folder.")
        sys.exit(1)

    # Load from Excel
    print(f"\nReading: {EXCEL_FILE}")
    records = load_from_excel(EXCEL_FILE)
    print(f"✓ Parsed {len(records)} records from Excel")

    # Preview
    print("\n── First 5 parsed records ────────────────────")
    for r in records[:5]:
        print(f"  [{r['distributor_id']}] #{r['priority_rank']}  {r['product_name']}")

    # Connect and seed
    print("\nConnecting to PostgreSQL...")
    conn = get_connection()
    cur = conn.cursor()

    create_table(cur)
    seed(records, cur)
    verify(cur)

    conn.commit()
    cur.close()
    conn.close()

    print("\n✅ Done — recommended_products table seeded successfully")
    print("   sku_recommendation_service.py will now return Excel-sourced products")