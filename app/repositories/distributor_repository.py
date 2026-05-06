from app.models.distributor import Distributor


class DistributorRepository:
    def __init__(self, db):
        self.db = db

    def get_by_distributor_id(self, distributor_id: str):
        return self.db.query(Distributor).filter(
            Distributor.distributor_id == distributor_id
        ).first()