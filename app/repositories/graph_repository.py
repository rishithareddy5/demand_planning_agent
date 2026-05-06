from app.core.falkor_db import graph


class GraphRepository:

    def get_recommendations_for_distributor(self, distributor_id: str, limit: int = 5):
        distributor_id = self._sanitize(distributor_id)
        limit = int(limit)

        # ---------------------------------------------------------
        # Primary logic (collaborative filtering):
        # 1. Find SKUs already distributed by target distributor
        # 2. Find other distributors who distribute the same SKUs
        # 3. Find additional SKUs those distributors also handle
        # 4. Exclude SKUs the target distributor already has
        # 5. Rank by how many other distributors carry them
        # ---------------------------------------------------------
        collaborative_query = f"""
        MATCH (d:Distributor {{distributor_id: '{distributor_id}'}})-[:DISTRIBUTES]->(owned:SKU)
        MATCH (other:Distributor)-[:DISTRIBUTES]->(owned)
        WHERE other.distributor_id <> '{distributor_id}'
        MATCH (other)-[:DISTRIBUTES]->(rec:SKU)
        WHERE NOT (d)-[:DISTRIBUTES]->(rec)
        RETURN
            rec.sku_id      AS sku_id,
            rec.name        AS sku_name,
            rec.category    AS category,
            COUNT(DISTINCT other) AS score
        ORDER BY score DESC, sku_name ASC
        LIMIT {limit}
        """

        result = graph.query(collaborative_query)
        recommendations = self._format_results(result)

        if recommendations:
            return recommendations

        # ---------------------------------------------------------
        # Fallback logic:
        # If no collaborative results, use category-based similarity.
        # Find SKUs in the same category as what the distributor carries
        # but that they don't carry yet.
        # ---------------------------------------------------------
        fallback_query = f"""
        MATCH (d:Distributor {{distributor_id: '{distributor_id}'}})-[:DISTRIBUTES]->(owned:SKU)
        MATCH (rec:SKU)
        WHERE rec.category = owned.category
          AND NOT (d)-[:DISTRIBUTES]->(rec)
          AND rec.sku_id <> owned.sku_id
        RETURN
            rec.sku_id   AS sku_id,
            rec.name     AS sku_name,
            rec.category AS category,
            COUNT(rec)   AS score
        ORDER BY score DESC, sku_name ASC
        LIMIT {limit}
        """

        fallback_result = graph.query(fallback_query)
        return self._format_results(fallback_result)

    def get_existing_skus_for_distributor(self, distributor_id: str):
        """
        Returns list of SKU IDs that the distributor already distributes.
        Called by FetchDistributorContextService to show existing SKUs
        in the context payload.
        """
        distributor_id = self._sanitize(distributor_id)

        query = f"""
        MATCH (d:Distributor {{distributor_id: '{distributor_id}'}})-[:DISTRIBUTES]->(s:SKU)
        RETURN s.sku_id AS sku_id, s.name AS sku_name, s.category AS category
        ORDER BY s.sku_id ASC
        """

        result = graph.query(query)

        if not result or not hasattr(result, "result_set"):
            return []

        skus = []
        for row in result.result_set:
            skus.append({
                "sku_id":   row[0],
                "sku_name": row[1],
                "category": row[2],
            })

        return skus

    def _format_results(self, result):
        recommendations = []

        if not result or not hasattr(result, "result_set"):
            return recommendations

        for row in result.result_set:
            recommendations.append({
                "sku_id":   row[0],
                "sku_name": row[1],
                "category": row[2],
                "score":    row[3],
            })

        return recommendations

    def _sanitize(self, value: str) -> str:
        return str(value).replace("\\", "\\\\").replace("'", "\\'")