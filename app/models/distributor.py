from sqlalchemy import Column, String
from app.core.database import Base


class Distributor(Base):
    __tablename__ = "distributors"

    distributor_id   = Column(String, primary_key=True)  # "D01", "D02" etc.
    distributor_name = Column(String)
    email            = Column(String)
    region           = Column(String)

    # Aliases so existing code doesn't break
    @property
    def distributor_code(self):
        return self.distributor_id

    @property
    def name(self):
        return self.distributor_name