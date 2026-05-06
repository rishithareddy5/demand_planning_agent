from pydantic import BaseModel
from typing import Dict


class ValidationResultSchema(BaseModel):
    total_records: int
    duplicate_rows: int
    negative_sales_values: int
    priority_distribution: Dict[str, int]
    unique_distributors: int
    cleaned_file_path: str