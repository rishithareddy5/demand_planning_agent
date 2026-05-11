from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_primary_sales_repository_query_and_save(monkeypatch):
    from app.repositories.primary_sales_repository import PrimarySalesRepository
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = ['row1']
    repo = PrimarySalesRepository(db)
    assert repo.get_sales_by_distributor('D01') == ['row1']

    saved = repo.save_cleaned_primary_sales([{'distributor_id': 'D01', 'sku_id': 'SKU01'}])
    assert len(saved) == 1
    db.add.assert_called_once()
    db.commit.assert_called_once()
    db.refresh.assert_called_once()


def test_distributor_repository_get_by_id(monkeypatch):
    from app.repositories.distributor_repository import DistributorRepository
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = 'D01-row'
    assert DistributorRepository(db).get_by_distributor_id('D01') == 'D01-row'


def test_fetch_distributor_context_aggregates_and_builds_response(monkeypatch):
    from app.services.fetch_distributor_context_service import FetchDistributorContextService
    service = FetchDistributorContextService(db=MagicMock())
    distributor = SimpleNamespace(distributor_code='D01', distributor_name='Revan', email='d@example.com', region='South')
    rows = [
        SimpleNamespace(sku_id='SKU01', sku_name='Malkist', category='Crackers', gross_dispatch_value=100, transaction_date=date(2024, 1, 1)),
        SimpleNamespace(sku_id='SKU01', sku_name='Malkist', category='Crackers', gross_dispatch_value=200, transaction_date=date(2024, 2, 1)),
    ]
    service.distributor_repo = MagicMock()
    service.sales_repo = MagicMock()
    service.graph_repo = MagicMock()
    service.distributor_repo.get_by_distributor_id.return_value = distributor
    service.sales_repo.get_sales_by_distributor.return_value = rows
    service.graph_repo.get_existing_skus_for_distributor.return_value = [{'sku_id': 'SKU01'}]

    result = service.execute('D01')

    assert result['distributor_name'] == 'Revan'
    assert result['historical_rows_count'] == 2
    assert result['unique_skus_purchased'] == 1
    assert result['sku_demand_signals'][0]['avg_quantity'] == 150


def test_fetch_distributor_context_unknown_distributor_raises():
    from app.services.fetch_distributor_context_service import FetchDistributorContextService
    service = FetchDistributorContextService(db=MagicMock())
    service.distributor_repo = MagicMock()
    service.distributor_repo.get_by_distributor_id.return_value = None
    import pytest
    with pytest.raises(ValueError):
        service.execute('BAD')


def test_graph_controller_route(monkeypatch):
    from app.controllers.graph_controller import router
    app = FastAPI()
    app.include_router(router)
    monkeypatch.setattr(
        'app.controllers.graph_controller.LoadNewProductsToGraphService',
        lambda: SimpleNamespace(execute=lambda: {'status': 'ok'})
    )
    assert TestClient(app).post('/graph/load-new-products').json() == {'status': 'ok'}


def test_recommendation_controller_function(monkeypatch):
    import app.services.build_demand_email_service as email_mod
    monkeypatch.setattr(email_mod, 'BuildDemandEmailService', lambda: None, raising=False)
    from app.controllers import recommendation_controller as rc
    monkeypatch.setattr(rc, 'FetchDistributorContextService', lambda db: SimpleNamespace(execute=lambda d: {'id': d}))
    monkeypatch.setattr(rc, 'SKURecommendationService', lambda: SimpleNamespace(execute=lambda d: {'recommendations': ['A']}))
    monkeypatch.setattr(rc, 'BuildDemandEmailService', lambda: SimpleNamespace(execute=lambda c, r: {'body': 'preview'}))

    result = rc.get_recommendations('D01', db=MagicMock())
    assert result['context'] == {'id': 'D01'}
    assert result['email_preview'] == {'body': 'preview'}
