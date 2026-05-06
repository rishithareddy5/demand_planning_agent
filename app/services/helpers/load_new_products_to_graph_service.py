from app.core.falkor_db import graph
from app.services.helpers.load_new_products_service import LoadNewProductsService


# --- IMPROVEMENT: Same hardened escape() as build_falkor_graph.py ---
# Applied consistently across all graph-writing services.
def escape(value: str) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("`", "\\`")
    )


class LoadNewProductsToGraphService:
    def __init__(self):
        self.loader = LoadNewProductsService()

    def execute(self):
        df = self.loader.execute()

        success_count = 0
        error_count = 0
        errors = []

        for idx, row in df.iterrows():
            try:
                sku_id = escape(row["SKU ID"])
                brand_family = escape(row["Brand Family"])
                sku_name = escape(row["SKU Name"])
                sku_description = escape(row["SKU Description"])
                category = escape(row["Category"])
                oem = escape(row["OEM"])
                priority = escape(row["Priority"])
                pack_size = escape(row["Pack Size"])
                variant_type = escape(row["Variant Type"])
                unit_cost = row["Unit Cost (₹)"]
                recommendation_strategy = escape(row["Recommendation Strategy"])
                target_channel = escape(row["Target Channel"])
                similar_existing_sku = escape(row["Similar to Existing SKU"])
                rationale = escape(row["Rationale"])

                try:
                    unit_cost_value = float(unit_cost) if unit_cost != "" else 0.0
                except Exception:
                    unit_cost_value = 0.0

                query = f"""
                MERGE (s:SKU {{id: '{sku_id}'}})
                SET s.name = '{sku_name}',
                    s.description = '{sku_description}',
                    s.brand_family = '{brand_family}',
                    s.category = '{category}',
                    s.oem = '{oem}',
                    s.priority = '{priority}',
                    s.pack_size = '{pack_size}',
                    s.variant_type = '{variant_type}',
                    s.unit_cost = {unit_cost_value},
                    s.recommendation_strategy = '{recommendation_strategy}',
                    s.target_channel = '{target_channel}',
                    s.rationale = '{rationale}',
                    s.is_new_product = true

                MERGE (c:Category {{name: '{category}'}})
                MERGE (b:BrandFamily {{name: '{brand_family}'}})

                MERGE (s)-[:BELONGS_TO]->(c)
                MERGE (s)-[:OF_BRAND]->(b)
                """
                graph.query(query)

                if similar_existing_sku:
                    similar_query = f"""
                    MATCH (existing:SKU {{id: '{similar_existing_sku}'}})
                    MATCH (newsku:SKU {{id: '{sku_id}'}})
                    MERGE (existing)-[:SIMILAR_TO]->(newsku)
                    """
                    graph.query(similar_query)

                success_count += 1

            # --- IMPROVEMENT: Per-row error isolation ---
            # Old version had no try/except — a single bad row would crash
            # the entire load, leaving the graph in a partial state with
            # no visibility into what failed.
            except Exception as e:
                error_count += 1
                errors.append({
                    "row_index": idx,
                    "sku_id": row.get("SKU ID", "unknown"),
                    "error": str(e)
                })
                print(f"[WARN] Skipped row {idx} (SKU: {row.get('SKU ID', '?')}): {e}")

        return {
            "message": "New products load complete",
            "success_count": success_count,
            "error_count": error_count,
            "errors": errors  # caller can log or surface these
        }
