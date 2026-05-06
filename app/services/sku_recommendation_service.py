from app.repositories.graph_repository import GraphRepository
from app.core.database import get_connection


class SKURecommendationService:
    def __init__(self):
        self.graph_repo = GraphRepository()

    def execute(self, distributor_id: str, graph_limit: int = 5, excel_limit: int = 5):
        # -----------------------------
        # 1. Get top 5 from FalkorDB
        # -----------------------------
        graph_recs = self.graph_repo.get_recommendations_for_distributor(
            distributor_id=distributor_id,
            limit=graph_limit
        )

        graph_products = [
            item.get("sku_name")
            for item in graph_recs
            if isinstance(item, dict) and item.get("sku_name")
        ]

        graph_products = graph_products[:graph_limit]

        # -----------------------------
        # 2. Get top 5 from PostgreSQL
        # -----------------------------
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT product_name
            FROM recommended_products
            WHERE distributor_id = %s
            ORDER BY priority_rank ASC
            LIMIT %s
        """, (distributor_id, excel_limit))

        rows = cursor.fetchall()

        cursor.close()
        conn.close()

        excel_products = [row[0] for row in rows]

        # -----------------------------
        # 3. Combine them
        #    Keep graph first, then Excel
        #    Avoid duplicates
        # -----------------------------
        final_products = []
        seen = set()

        for product in graph_products:
            if product not in seen:
                final_products.append(product)
                seen.add(product)

        for product in excel_products:
            if product not in seen:
                final_products.append(product)
                seen.add(product)

        return {
            "distributor_id": distributor_id,
            "graph_recommendations": graph_products,
            "excel_recommendations": excel_products,
            "recommendations": final_products
        }


def get_recommended_products(distributor_id: str, graph_limit: int = 5, excel_limit: int = 5):
    service = SKURecommendationService()
    result = service.execute(
        distributor_id=distributor_id,
        graph_limit=graph_limit,
        excel_limit=excel_limit
    )
    return result.get("recommendations", [])