from app.core.database import SessionLocal
from app.repositories.distributor_repository import DistributorRepository
from app.services.helpers.fetch_distributor_context_service import (
    FetchDistributorContextService,
)


class DistributorService:
    def __init__(self) -> None:
        self.distributor_repository = DistributorRepository()

    def get_distributor_context(self, distributor_code: str) -> dict:
        distributor = self.distributor_repository.get_by_code(distributor_code)

        if not distributor:
            raise ValueError(f"Distributor '{distributor_code}' not found")

        distributor["distributor_id"] = str(distributor["distributor_id"])

        enrichment = self._fetch_enrichment(distributor["distributor_id"])
        distributor.update(enrichment)

        return distributor

    def _fetch_enrichment(self, distributor_id: str) -> dict:
        with SessionLocal() as session:
            fetch_service = FetchDistributorContextService(session)
            try:
                enrichment = fetch_service.execute(distributor_id)
            except Exception:
                # PostgreSQL remains the source of record. If enrichment fails,
                # return the base distributor payload instead of failing the request.
                return {}

        if not isinstance(enrichment, dict):
            return {}

        allowed_fields = {
            "historical_rows_count",
            "existing_skus",
            "sku_demand_signals",
            "unique_skus_purchased",
        }
        return {
            key: enrichment[key]
            for key in allowed_fields
            if key in enrichment
        }
