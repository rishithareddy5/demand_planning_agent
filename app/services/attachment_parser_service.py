import re
import pandas as pd
from typing import Any, Dict, List, Optional, Tuple

from app.services.reply_parser_service import match_sku
from app.data.sku_data import get_sku_map, get_sku_id_to_name


POSSIBLE_SKU_ID_COLUMNS = [
    "sku_id",
    "sku id",
    "sku_code",
    "sku code",
    "item_code",
    "item code",
    "product_code",
    "product code",
]

POSSIBLE_PRODUCT_COLUMNS = [
    "sku_name",
    "sku name",
    "product",
    "product_name",
    "product name",
    "item",
    "item_name",
    "item name",
    "description",
    "sku",
]

POSSIBLE_QTY_COLUMNS = [
    "qty",
    "quantity",
    "order_qty",
    "order quantity",
    "demand",
    "units",
    "pieces",
    "pcs",
]


def normalize_text(value: Any) -> str:
    return " ".join(str(value).strip().lower().split())


def normalize_column_name(col: str) -> str:
    return normalize_text(str(col).replace("_", " "))


def find_best_column(columns: List[str], candidates: List[str]) -> Optional[str]:
    normalized_map = {normalize_column_name(col): col for col in columns}

    for candidate in candidates:
        if candidate in normalized_map:
            return normalized_map[candidate]

    for normalized, original in normalized_map.items():
        for candidate in candidates:
            if candidate in normalized:
                return original

    return None


def extract_numeric_quantity(value: Any) -> Optional[int]:
    if pd.isna(value):
        return None

    text = str(value).strip()
    match = re.search(r"-?\d+", text)
    if not match:
        return None

    quantity = int(match.group())
    return quantity


def exact_name_match(product_text: str) -> Tuple[Optional[str], Optional[str], int]:
    sku_map = get_sku_map()
    normalized_product = normalize_text(product_text)

    if normalized_product in sku_map:
        return sku_map[normalized_product], normalized_product, 100

    return None, None, 0


def exact_sku_id_match(sku_value: Any) -> Tuple[Optional[str], Optional[str], int]:
    if pd.isna(sku_value):
        return None, None, 0

    sku_id_to_name = get_sku_id_to_name()
    sku_id = str(sku_value).strip().upper()

    if sku_id in sku_id_to_name:
        return sku_id, sku_id_to_name[sku_id], 100

    return None, None, 0


def resolve_product(
    product_text: str,
    sku_id_value: Any = None,
    min_fuzzy_score: int = 90
) -> Tuple[Optional[str], Optional[str], int, str]:
    """
    Resolution order:
    1. exact sku_id match
    2. exact normalized sku_name match
    3. strict fuzzy match
    """
    sku_id, sku_name, score = exact_sku_id_match(sku_id_value)
    if sku_id:
        return sku_id, sku_name, score, "exact_sku_id"

    sku_id, sku_name, score = exact_name_match(product_text)
    if sku_id:
        return sku_id, sku_name, score, "exact_name"

    sku_id, sku_name, score = match_sku(product_text, min_score=min_fuzzy_score)
    if sku_id:
        return sku_id, sku_name, score, "fuzzy_name"

    return None, None, 0, "unmatched"


def parse_excel_file(file_path: str) -> List[Dict[str, Any]]:
    parsed_items: List[Dict[str, Any]] = []

    excel_data = pd.read_excel(file_path, sheet_name=None)

    for sheet_name, df in excel_data.items():
        if df.empty:
            continue

        df.columns = [str(col).strip() for col in df.columns]

        sku_id_col = find_best_column(list(df.columns), POSSIBLE_SKU_ID_COLUMNS)
        product_col = find_best_column(list(df.columns), POSSIBLE_PRODUCT_COLUMNS)
        qty_col = find_best_column(list(df.columns), POSSIBLE_QTY_COLUMNS)

        # quantity is mandatory
        if not qty_col:
            continue

        # at least one of sku_id or product must exist
        if not sku_id_col and not product_col:
            continue

        for _, row in df.iterrows():
            sku_id_value = row.get(sku_id_col) if sku_id_col else None
            product_value = row.get(product_col) if product_col else None
            qty_value = row.get(qty_col)

            quantity = extract_numeric_quantity(qty_value)

            # skip invalid / zero / negative demand
            if quantity is None or quantity <= 0:
                continue

            product_text = ""
            if product_value is not None and not pd.isna(product_value):
                product_text = str(product_value).strip()

            sku_id, sku_name, match_score, match_type = resolve_product(
                product_text=product_text,
                sku_id_value=sku_id_value,
                min_fuzzy_score=90
            )

            # skip unmatched rows rather than guessing wrong
            if not sku_id:
                continue

            parsed_items.append({
                "sku_id": sku_id,
                "sku_name": sku_name,
                "quantity": quantity,
                "unit": None,
                "matched_text": f"{product_text or sku_id_value} | {quantity}",
                "match_score": match_score,
                "source": "excel_attachment",
                "sheet_name": sheet_name,
                "match_type": match_type,
            })

    return parsed_items


def is_excel_attachment(filename: str) -> bool:
    if not filename:
        return False

    lower_name = filename.lower()
    return lower_name.endswith(".xlsx") or lower_name.endswith(".xls")