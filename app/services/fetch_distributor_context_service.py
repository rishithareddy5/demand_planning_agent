from app.repositories.primary_sales_repository import PrimarySalesRepository
from app.repositories.graph_repository import GraphRepository
from app.repositories.distributor_repository import DistributorRepository


class FetchDistributorContextService:
    def __init__(self, db):
        self.sales_repo = PrimarySalesRepository(db)
        self.graph_repo = GraphRepository()
        self.distributor_repo = DistributorRepository(db)  # ✅ NEW





    def execute(self, distributor_id: str):
        distributor = self._get_distributor(distributor_id)

        sales_rows = self.sales_repo.get_sales_by_distributor(distributor_id)
        existing_skus = self.graph_repo.get_existing_skus_for_distributor(distributor_id)

        sku_demand_map = self._aggregate_demand(sales_rows)
        sku_demand_list = self._prepare_response_list(sku_demand_map)

        return self._build_response(distributor, sales_rows, existing_skus, sku_demand_map, sku_demand_list)

    def _get_distributor(self, distributor_id):
        distributor = self.distributor_repo.get_by_distributor_id(distributor_id)

        if not distributor:
            raise ValueError(f"Distributor not found: {distributor_id}")

        return distributor
    
    def _aggregate_demand(self, sales_rows):
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
            entry["total_quantity"] += row.gross_dispatch_value or 0
            entry["order_count"] += 1

            txn_date = getattr(row, "transaction_date", None)
            if txn_date:
                if entry["last_purchase_date"] is None or txn_date > entry["last_purchase_date"]:
                    entry["last_purchase_date"] = txn_date

        # compute averages
        for entry in sku_demand_map.values():
            entry["avg_quantity"] = (
                round(entry["total_quantity"] / entry["order_count"], 2)
                if entry["order_count"] > 0
                else 0
            )

        return sku_demand_map

    def _prepare_response_list(self, sku_demand_map):
        sku_demand_list = []

        for entry in sku_demand_map.values():
            entry = entry.copy()

            if entry["last_purchase_date"]:
                entry["last_purchase_date"] = entry["last_purchase_date"].isoformat()

            sku_demand_list.append(entry)

        return sku_demand_list


    def _build_response(self, distributor, sales_rows, existing_skus, sku_demand_map, sku_demand_list):
        return {
            "distributor_id": distributor.distributor_code,
            "distributor_name": distributor.distributor_name,
            "email": distributor.email,
            "region": distributor.region,

            "historical_rows_count": len(sales_rows),
            "existing_skus": existing_skus,
            "sku_demand_signals": sku_demand_list,
            "unique_skus_purchased": len(sku_demand_map),
        }