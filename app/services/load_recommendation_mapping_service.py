import pandas as pd
from app.core.constants import NEW_PRODUCTS_FILE


class LoadRecommendationMappingService:
    """
    Loads distributor-wise recommended products from
    sheet '3. Recommendation Mapping'
    """

    def execute(self):
        df = pd.read_excel(
            NEW_PRODUCTS_FILE,
            sheet_name="3. Recommendation Mapping",
            header=None
        )

        df = df.iloc[2:].copy()
        df.columns = ["Distributor", "SKU_ID", "Product", "Reason"]

        current_distributor = None
        records = []

        for _, row in df.iterrows():

            if pd.notna(row["Distributor"]):
                current_distributor = str(row["Distributor"]).strip()

            if pd.isna(row["SKU_ID"]) or str(row["SKU_ID"]).strip() == "SKU ID":
                continue

            if not current_distributor:
                continue

            distributor_id = current_distributor.split(" ")[0].strip()

            records.append({
                "distributor_id": distributor_id,
                "product": str(row["Product"]).strip(),
                "reason": str(row["Reason"]).strip() if pd.notna(row["Reason"]) else ""
            })

        return records

    def group_by_distributor(self):
        records = self.execute()
        grouped = {}

        for record in records:
            distributor_id = record["distributor_id"]
            grouped.setdefault(distributor_id, []).append(record)

        return grouped