from itertools import combinations
from collections import defaultdict

from app.core.database import SessionLocal
from app.repositories.primary_sales_repository import PrimarySalesRepository
from app.core.falkor_db import graph


# --- IMPROVEMENT: Hardened escape() ---
# Old version only handled backslashes and single quotes.
# New version also strips newlines and carriage returns which would
# break multi-line Cypher strings and cause silent query failures.
def escape(value: str) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("`", "\\`")
    )


def build_graph():
    db = SessionLocal()
    repo = PrimarySalesRepository(db)
    sales = repo.get_all_sales()

    distributor_to_skus = defaultdict(set)

    for row in sales:
        distributor_id = escape(row.distributor_id)
        sku_id = escape(row.sku_id)
        sku_name = escape(row.sku_name)
        category = escape(row.category or "Unknown")

        distributor_to_skus[row.distributor_id].add(row.sku_id)

        query = f"""
        MERGE (d:Distributor {{id: '{distributor_id}'}})
        MERGE (s:SKU {{id: '{sku_id}'}})
        ON CREATE SET s.name = '{sku_name}'
        ON MATCH SET s.name = '{sku_name}'
        MERGE (c:Category {{name: '{category}'}})
        MERGE (d)-[:BOUGHT]->(s)
        MERGE (s)-[:BELONGS_TO]->(c)
        """
        graph.query(query)

    # Build SKU-SKU co-purchase edges
    for distributor_id, sku_set in distributor_to_skus.items():
        for sku1, sku2 in combinations(sorted(sku_set), 2):
            sku1_e = escape(sku1)
            sku2_e = escape(sku2)

            query = f"""
            MATCH (s1:SKU {{id: '{sku1_e}'}})
            MATCH (s2:SKU {{id: '{sku2_e}'}})
            MERGE (s1)-[r:BOUGHT_WITH]->(s2)
            ON CREATE SET r.weight = 1
            ON MATCH SET r.weight = r.weight + 1
            MERGE (s2)-[r2:BOUGHT_WITH]->(s1)
            ON CREATE SET r2.weight = 1
            ON MATCH SET r2.weight = r2.weight + 1
            """
            graph.query(query)

    db.close()
    print("FalkorDB graph built successfully.")


if __name__ == "__main__":
    build_graph()