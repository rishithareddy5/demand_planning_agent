import pandas as pd
from app.core.constants import NEW_PRODUCTS_FILE, NEW_PRODUCTS_SHEET


class LoadNewProductsService:
    def execute(self):
        df = pd.read_excel(
            NEW_PRODUCTS_FILE,
            sheet_name=NEW_PRODUCTS_SHEET,
            header=2
        )

        # Remove fully empty rows
        df = df.dropna(how="all").copy()

        # Standardize column names
        df.columns = [str(col).strip() for col in df.columns]

        # Keep only required columns
        required_columns = [
            "SKU ID",
            "Brand Family",
            "SKU Name",
            "SKU Description",
            "Category",
            "OEM",
            "Priority",
            "Pack Size",
            "Variant Type",
            "Unit Cost (₹)",
            "Recommendation Strategy",
            "Target Channel",
            "Similar to Existing SKU",
            "Rationale"
        ]

        missing = [col for col in required_columns if col not in df.columns]
        if missing:
            raise ValueError(f"Missing columns in new products file: {missing}")

        df = df[required_columns].copy()

        # Fill NaN values
        df = df.fillna("")

        return df