from unittest.mock import patch

from app.services.reply_parser_service import (
    aggregate_items,
    calculate_confidence,
    clean_email_body,
    classify_reply,
    extract_quantity_and_unit,
    get_distributor_id,
    match_sku,
    normalize_product_text,
    parse_demand_lines,
    parse_reply,
    remove_quantity_words,
    split_reply_into_lines,
    strip_list_numbering,
)


def test_clean_email_body_removes_quoted_thread():
    body = "MALKIST CHEESE 48 PCS X 72 - 100\n\nOn Mon, Team wrote:\n> old mail"
    result = clean_email_body(body)
    assert "old mail" not in result
    assert "MALKIST" in result


def test_split_reply_into_lines_supports_multiple_separators():
    lines = split_reply_into_lines("MALKIST - 100; BENG BENG - 200 | KOPIKO - 50")
    assert len(lines) == 3


def test_classify_reply_types():
    assert classify_reply("Will send soon") == "informational"
    assert classify_reply("Same as last month") == "reference"
    assert classify_reply("No demand this month") == "negative"
    assert classify_reply("MALKIST - 100") == "demand"
    assert classify_reply("hello team") == "ambiguous"


def test_get_distributor_id_from_email_and_body(distributor_map):
    with patch("app.services.reply_parser_service.get_distributor_map", return_value=distributor_map):
        assert get_distributor_id("revanbejagam@gmail.com", "") == "D01"
        assert get_distributor_id("unknown@example.com", "my distributor id is D03") == "D03"
        assert get_distributor_id("unknown@example.com", "") == "UNKNOWN"


def test_quantity_unit_and_list_numbering_helpers():
    assert strip_list_numbering("1. MALKIST - 100") == "MALKIST - 100"
    assert extract_quantity_and_unit("SKU01 MALKIST 48 PCS - 100 boxes") == (100, "pcs")
    assert extract_quantity_and_unit("No number here") == (None, None)


def test_text_normalization_helpers():
    assert normalize_product_text("  BENG   BENG  ") == "beng beng"
    assert remove_quantity_words("1. Need 100 boxes of MALKIST CHEESE") == "malkist cheese"


def test_match_sku_by_code_and_name():
    assert match_sku("SKU01 - 100")[0] == "SKU01"
    sku_id, sku_name, score = match_sku("MALKIST CHEESE 48 PCS X 72 - 100", min_score=70)
    assert sku_id == "SKU01"
    assert score >= 70


def test_parse_demand_lines_and_aggregate_items():
    items = parse_demand_lines([
        "MALKIST CHEESE 48 PCS X 72 - 100",
        "MALKIST CHEESE 48 PCS X 72 - 50",
        "BENG BENG WAFER 22GM - 200",
    ])
    aggregated = aggregate_items(items)
    assert len(aggregated) == 2
    assert next(i for i in aggregated if i["sku_id"] == "SKU01")["quantity"] == 150


def test_calculate_confidence_paths():
    assert calculate_confidence("D01", [], "informational") == 0.9
    assert calculate_confidence("UNKNOWN", [], "informational") == 0.6
    assert calculate_confidence("D01", [], "demand") == 0.2
    value = calculate_confidence("D01", [{"sku_id": "SKU01", "quantity": 10, "match_score": 95}], "demand")
    assert 0.75 <= value <= 1.0


def test_parse_reply_end_to_end_known_distributor(distributor_map):
    with patch("app.services.reply_parser_service.get_distributor_map", return_value=distributor_map):
        result = parse_reply("revanbejagam@gmail.com", "MALKIST CHEESE 48 PCS X 72 - 100")
    assert result["distributor_id"] == "D01"
    assert result["reply_type"] == "demand"
    assert result["items"][0]["sku_id"] == "SKU01"
    assert result["needs_followup"] is False


def test_parse_reply_non_demand_paths(distributor_map):
    with patch("app.services.reply_parser_service.get_distributor_map", return_value=distributor_map):
        assert parse_reply("revanbejagam@gmail.com", "Will send later")["needs_followup"] is True
        assert parse_reply("revanbejagam@gmail.com", "Same as last month")["reply_type"] == "reference"
        assert parse_reply("revanbejagam@gmail.com", "Nil")["needs_followup"] is False
        assert parse_reply("revanbejagam@gmail.com", "Thank you")["reply_type"] == "ambiguous"
