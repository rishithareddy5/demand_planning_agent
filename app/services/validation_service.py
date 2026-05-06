import pandas as pd


def clean_primary_sales(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Clean column names
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

    # Remove duplicate rows
    df = df.drop_duplicates()

    # Remove fully empty rows
    df = df.dropna(how="all")

    # Remove extra spaces from text columns
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).str.strip()

    # Replace empty-like text values with proper null
    df = df.replace(["", "nan", "None", "null"], pd.NA)

    # Convert date column if present
    if "transaction_date" in df.columns:
        df["transaction_date"] = pd.to_datetime(df["transaction_date"], errors="coerce")

    # Convert numeric columns if present
    numeric_cols = [
        "opening_stock_quantity",
        "remaining_quantity",
        "gross_dispatch_value",
        "tax_amount",
        "unit_base_cost",
        "regional_demand_multiplier"
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Fill missing text values
    text_cols = [
        "sku_name",
        "product_category_snapshot",
        "priority_flag",
        "distribution_channel_type",
        "distributor_priority_tier",
        "mapping_status"
    ]

    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].fillna("Unknown")

    # Fill missing numeric values
    for col in numeric_cols:
        if col in df.columns:
            df[col] = df[col].fillna(0)

    # Normalize priority flag
    if "priority_flag" in df.columns:
        df["priority_flag"] = df["priority_flag"].str.title()

    return df


def validate_primary_sales(df: pd.DataFrame) -> dict:
    results = {
        "total_records": len(df),
        "duplicate_rows": int(df.duplicated().sum()),
        "negative_sales_values": 0,
        "priority_distribution": {},
        "unique_distributors": 0,
    }

    if "gross_dispatch_value" in df.columns:
        results["negative_sales_values"] = int((df["gross_dispatch_value"] < 0).sum())

    if "priority_flag" in df.columns:
        results["priority_distribution"] = df["priority_flag"].value_counts().to_dict()

    if "distributor_id" in df.columns:
        results["unique_distributors"] = int(df["distributor_id"].nunique())

    return results