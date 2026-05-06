from app.repositories.primary_sales_repository import PrimarySalesRepository
from app.repositories.graph_repository import GraphRepository


class FetchDistributorContextService:
    def __init__(self, db):
        self.sales_repo = PrimarySalesRepository(db)
        self.graph_repo = GraphRepository()

    def execute(self, distributor_id: str):
        sales_rows = self.sales_repo.get_sales_by_distributor(distributor_id)
        existing_skus = self.graph_repo.get_existing_skus_for_distributor(distributor_id)

        # --- IMPROVEMENT: Aggregate demand signals per SKU ---
        # Previously only row count was returned, giving downstream services
        # no real data to make demand-aware recommendations.
        sku_demand_map = {}
        for row in sales_rows:
            sku_id = row.sku_id
            if sku_id not in sku_demand_map:
                sku_demand_map[sku_id] = {
                    "sku_id": sku_id,
                    "sku_name": row.sku_name,
                    "category": row.category or "Unknown",
                    "total_quantity": 0,
                    "order_count": 0,
                    "last_purchase_date": None,
                }

            entry = sku_demand_map[sku_id]
            quantity = (
                getattr(row, "sales_qty", None)
                or getattr(row, "order_qty", None)
                or getattr(row, "gross_dispatch_value", None)
                or 0
            )
            entry["total_quantity"] += quantity
            entry["order_count"] += 1

            # Track most recent purchase date
            txn_date = (
                getattr(row, "sale_date", None)
                or getattr(row, "order_date", None)
                or getattr(row, "transaction_date", None)
            )
            if txn_date:
                if entry["last_purchase_date"] is None or txn_date > entry["last_purchase_date"]:
                    entry["last_purchase_date"] = txn_date

        # Compute average quantity per SKU
        for entry in sku_demand_map.values():
            entry["avg_quantity"] = (
                round(entry["total_quantity"] / entry["order_count"], 2)
                if entry["order_count"] > 0
                else 0
            )

        # Convert dates to ISO strings for JSON-safety
        sku_demand_list = []
        for entry in sku_demand_map.values():
            entry = entry.copy()
            if entry["last_purchase_date"]:
                entry["last_purchase_date"] = entry["last_purchase_date"].isoformat()
            sku_demand_list.append(entry)

        return {
            "distributor_id": distributor_id,
            "historical_rows_count": len(sales_rows),      # kept for backward compat
            "existing_skus": existing_skus,
            "sku_demand_signals": sku_demand_list,          # NEW: per-SKU demand aggregates
            "unique_skus_purchased": len(sku_demand_map),   # NEW: quick count
        }
