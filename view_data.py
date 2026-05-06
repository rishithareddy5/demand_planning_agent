import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()


def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT"),
        database=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )


def get_all_replies():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            r.id,
            r.distributor_id,
            r.from_email,
            r.reply_type,
            r.confidence,
            i.sku_name,
            i.quantity
        FROM parsed_replies r
        LEFT JOIN parsed_reply_items i
        ON r.id = i.parsed_reply_id
        ORDER BY r.id DESC;
    """)

    rows = cur.fetchall()

    cur.close()
    conn.close()

    return rows


if __name__ == "__main__":
    rows = get_all_replies()

    print("\nALL REPLIES FROM DATABASE:\n")

    for row in rows:
        print(row)