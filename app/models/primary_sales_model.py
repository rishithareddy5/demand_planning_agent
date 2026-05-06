from sqlalchemy import Column, Integer, String, Numeric, Date
from app.core.database import Base


class PrimarySales(Base):
    __tablename__ = "primary_sales"

    id = Column(Integer, primary_key=True, index=True)
    distributor_id = Column(String(50), nullable=False)
    sku_id = Column(String(50), nullable=False)
    sku_name = Column(String(255), nullable=False)
    category = Column(String(255), nullable=True)
    order_qty = Column(Numeric, nullable=True)
    order_value = Column(Numeric, nullable=True)
    order_date = Column(Date, nullable=True)