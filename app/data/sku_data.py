import pandas as pd
from typing import Dict, List, Optional

SKU_MAP: Dict[str, str] = {}
SKU_NAME_LIST: List[str] = []
SKU_ID_TO_NAME: Dict[str, str] = {}


def normalize_text(value: str) -> str:
    return " ".join(str(value).strip().lower().split())


def _find_header_row(file_path: str, max_rows_to_check: int = 10) -> int:
    preview = pd.read_excel(file_path, sheet_name=0, header=None, nrows=max_rows_to_check)

    sku_id_candidates = ["sku id", "sku_id", "sku code", "product code", "item code"]
    sku_name_candidates = ["sku name", "sku_name", "product name", "item name", "description", "product"]

    for idx in range(len(preview)):
        row_values = [normalize_text(v) for v in preview.iloc[idx].tolist() if pd.notna(v)]
        has_id = any(any(c == cell for c in sku_id_candidates) for cell in row_values)
        has_name = any(any(c == cell for c in sku_name_candidates) for cell in row_values)
        if has_id and has_name:
            return idx

    raise ValueError(
        f"Could not find header row in first {max_rows_to_check} rows of recommended products file."
    )


def _detect_columns(df: pd.DataFrame, file_label: str) -> pd.DataFrame:
    df.columns = [str(col).strip().lower().replace("_", " ") for col in df.columns]

    sku_id_candidates = ["sku id", "sku_id", "sku code", "product code", "item code"]
    sku_name_candidates = ["sku name", "sku_name", "product name", "item name", "description", "product"]

    sku_id_col = None
    sku_name_col = None

    for col in df.columns:
        if any(candidate in col for candidate in sku_id_candidates):
            sku_id_col = col
            break

    for col in df.columns:
        if any(candidate in col for candidate in sku_name_candidates):
            sku_name_col = col
            break

    if not sku_id_col or not sku_name_col:
        raise ValueError(
            f"Could not find SKU columns in {file_label}. Found columns: {df.columns.tolist()}"
        )

    df = df[[sku_id_col, sku_name_col]].dropna().drop_duplicates()
    df = df.rename(columns={sku_id_col: "sku_id", sku_name_col: "sku_name"})
    df["sku_id"] = df["sku_id"].astype(str).str.strip().str.upper()
    df["sku_name"] = df["sku_name"].astype(str).apply(normalize_text)

    return df


def _load_primary_sales(file_path: str) -> pd.DataFrame:
    df = pd.read_excel(file_path)
    return _detect_columns(df, "primary sales file")


def _load_recommended_products(file_path: str) -> pd.DataFrame:
    header_row = _find_header_row(file_path)
    df = pd.read_excel(file_path, sheet_name=0, header=header_row)
    return _detect_columns(df, "recommended products file")


def load_sku_data(
    primary_sales_file: str,
    recommended_products_file: Optional[str] = None
) -> None:
    global SKU_MAP, SKU_NAME_LIST, SKU_ID_TO_NAME

    primary_df = _load_primary_sales(primary_sales_file)
    all_frames = [primary_df]

    if recommended_products_file:
        recommended_df = _load_recommended_products(recommended_products_file)
        all_frames.append(recommended_df)

    combined_df = pd.concat(all_frames, ignore_index=True)
    combined_df = combined_df.dropna(subset=["sku_id", "sku_name"])
    combined_df = combined_df.drop_duplicates(subset=["sku_id"])
    combined_df = combined_df.drop_duplicates(subset=["sku_name"])

    SKU_MAP = dict(zip(combined_df["sku_name"], combined_df["sku_id"]))
    SKU_NAME_LIST = list(SKU_MAP.keys())
    SKU_ID_TO_NAME = dict(zip(combined_df["sku_id"], combined_df["sku_name"]))


def get_sku_map() -> Dict[str, str]:
    return SKU_MAP


def get_sku_names() -> List[str]:
    return SKU_NAME_LIST


def get_sku_id_to_name() -> Dict[str, str]:
    return SKU_ID_TO_NAME