from typing import Any, Dict, List
from sqlalchemy.orm import Session
from app.models.primary_sales_model import PrimarySales


class PrimarySalesRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all_sales(self):
        return self.db.query(PrimarySales).all()

    def get_sales_by_distributor(self, distributor_id: str):
        return (
            self.db.query(PrimarySales)
            .filter(PrimarySales.distributor_id == distributor_id)
            .all()
        )

    def load_primary_sales(self):
        return self.get_all_sales()

    def save_cleaned_primary_sales(self, cleaned_rows: List[Dict[str, Any]]):
        saved_records = []

        for row in cleaned_rows:
            sale = PrimarySales(**row)
            self.db.add(sale)
            saved_records.append(sale)

        self.db.commit()

        for record in saved_records:
            self.db.refresh(record)

        return saved_records


def load_primary_sales(db: Session):
    repo = PrimarySalesRepository(db)
    return repo.load_primary_sales()


def save_cleaned_primary_sales(db: Session, cleaned_rows: List[Dict[str, Any]]):
    repo = PrimarySalesRepository(db)
    return repo.save_cleaned_primary_sales(cleaned_rows)