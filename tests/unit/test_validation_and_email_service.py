import pandas as pd

from app.services.build_demand_email_service import build_demand_email
from app.services.validation_service import clean_primary_sales, validate_primary_sales
from tests.conftest import valid_primary_sales_df


def test_clean_primary_sales_normalizes_columns_and_values(valid_primary_sales_df):
    dirty = pd.concat([valid_primary_sales_df, valid_primary_sales_df.iloc[[0]]], ignore_index=True)
    cleaned = clean_primary_sales(dirty)
    assert "transaction_date" in cleaned.columns
    assert "gross_dispatch_value" in cleaned.columns
    assert len(cleaned) == len(valid_primary_sales_df)
    assert cleaned["priority_flag"].tolist() == ["High", "Medium"]
    assert pd.api.types.is_datetime64_any_dtype(cleaned["transaction_date"])


def test_clean_primary_sales_handles_missing_values(valid_primary_sales_df):
    valid_primary_sales_df.loc[0, "SKU Name"] = ""
    #valid_primary_sales_df.loc[0, "Gross Dispatch Value"] = "bad"
    valid_primary_sales_df["Gross Dispatch Value"] = valid_primary_sales_df["Gross Dispatch Value"].astype(object)
    valid_primary_sales_df.loc[0, "Gross Dispatch Value"] = "bad"
    cleaned = clean_primary_sales(valid_primary_sales_df)
    assert cleaned["sku_name"].isna().sum() == 0 or "Unknown" in cleaned["sku_name"].values
    assert cleaned["gross_dispatch_value"].iloc[0] == 0


def test_validate_primary_sales_reports_quality_metrics():
    df = pd.DataFrame({
        "distributor_id": ["D01", "D01", "D02"],
        "sku_id": ["SKU01", "SKU01", "SKU04"],
        "gross_dispatch_value": [100, -10, 50],
        "priority_flag": ["High", "High", "Medium"],
    })
    result = validate_primary_sales(df)
    assert result["total_records"] == 3
    assert result["negative_sales_values"] == 1
    assert result["unique_distributors"] == 2
    assert result["priority_distribution"]["High"] == 2


def test_build_demand_email_with_and_without_recommendations():
    with_recs = build_demand_email("D01", "dist@example.com", ["MALKIST", "KOPIKO"])
    assert with_recs["to_email"] == "dist@example.com"
    assert "D01" in with_recs["body"]
    assert "1. MALKIST" in with_recs["body"]
    without_recs = build_demand_email("D02", "d2@example.com", [])
    assert "No recommendations" in without_recs["body"]
