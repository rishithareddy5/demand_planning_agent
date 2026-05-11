import pandas as pd

from app.services.attachment_parser_service import (
    _process_sheet,
    exact_name_match,
    exact_sku_id_match,
    extract_numeric_quantity,
    find_best_column,
    is_excel_attachment,
    normalize_column_name,
    normalize_text,
    parse_excel_file,
    resolve_product,
)


def test_normalizers_and_column_finder():
    assert normalize_text("  SKU   Name ") == "sku name"
    assert normalize_column_name("sku_name") == "sku name"
    assert find_best_column(["Product Name", "Quantity"], ["product name"]) == "Product Name"
    assert find_best_column(["Order Quantity"], ["quantity"]) == "Order Quantity"


def test_quantity_extraction_and_attachment_detection():
    assert extract_numeric_quantity("100 boxes") == 100
    assert extract_numeric_quantity("-5") == -5
    assert extract_numeric_quantity("none") is None
    assert is_excel_attachment("demand.xlsx") is True
    assert is_excel_attachment("image.png") is False


def test_exact_and_resolve_product():
    assert exact_sku_id_match("SKU01")[0] == "SKU01"
    assert exact_name_match("MALKIST CHEESE  48 PCS X 72")[0] == "SKU01"
    sku_id, _, score, match_type = resolve_product("MALKIST CHEESE 48 PCS X 72", None, min_fuzzy_score=70)
    assert sku_id == "SKU01"
    assert score >= 70
    assert match_type in {"exact_name", "fuzzy_name"}


def test_process_sheet_skips_invalid_rows():
    df = pd.DataFrame({
        "sku_id": ["SKU01", "SKU04", "BAD"],
        "sku_name": ["MALKIST CHEESE  48 PCS X 72", "BENG BENG WAFER 22GM", "UNKNOWN"],
        "Quantity": [100, 0, 50],
    })
    items = _process_sheet(df, "Sheet1")
    assert len(items) == 1
    assert items[0]["sku_id"] == "SKU01"


def test_parse_excel_file_multiple_sheets(tmp_path):
    file_path = tmp_path / "demand.xlsx"
    with pd.ExcelWriter(file_path) as writer:
        pd.DataFrame({"sku_id": ["SKU01"], "Quantity": [100]}).to_excel(writer, sheet_name="A", index=False)
        pd.DataFrame({"Product Name": ["BENG BENG WAFER 22GM"], "qty": [200]}).to_excel(writer, sheet_name="B", index=False)
    items = parse_excel_file(str(file_path))
    assert {item["sku_id"] for item in items} == {"SKU01", "SKU04"}
