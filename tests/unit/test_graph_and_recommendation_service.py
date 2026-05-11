from unittest.mock import MagicMock, patch

from app.repositories.graph_repository import GraphRepository
from app.services.sku_recommendation_service import SKURecommendationService, get_recommended_products


class Result:
    def __init__(self, rows):
        self.result_set = rows


def test_graph_repository_formats_collaborative_results(monkeypatch):
    repo = GraphRepository()
    fake_graph = MagicMock()
    fake_graph.query.return_value = Result([['SKU09', 'NEW SKU', 'Snacks', 3]])
    monkeypatch.setattr('app.repositories.graph_repository.graph', fake_graph)

    recs = repo.get_recommendations_for_distributor("D'01", limit=2)

    assert recs == [{'sku_id': 'SKU09', 'sku_name': 'NEW SKU', 'category': 'Snacks', 'score': 3}]
    assert "D\\'01" in fake_graph.query.call_args.args[0]


def test_graph_repository_uses_fallback_when_first_query_empty(monkeypatch):
    repo = GraphRepository()
    fake_graph = MagicMock()
    fake_graph.query.side_effect = [Result([]), Result([['SKU10', 'FALLBACK', 'Wafers', 1]])]
    monkeypatch.setattr('app.repositories.graph_repository.graph', fake_graph)

    recs = repo.get_recommendations_for_distributor('D01')

    assert recs[0]['sku_name'] == 'FALLBACK'
    assert fake_graph.query.call_count == 2


def test_existing_skus_returns_empty_for_bad_result(monkeypatch):
    fake_graph = MagicMock()
    fake_graph.query.return_value = None
    monkeypatch.setattr('app.repositories.graph_repository.graph', fake_graph)

    assert GraphRepository().get_existing_skus_for_distributor('D01') == []


def test_existing_skus_formats_rows(monkeypatch):
    fake_graph = MagicMock()
    fake_graph.query.return_value = Result([['SKU01', 'MALKIST', 'Crackers']])
    monkeypatch.setattr('app.repositories.graph_repository.graph', fake_graph)

    assert GraphRepository().get_existing_skus_for_distributor('D01') == [
        {'sku_id': 'SKU01', 'sku_name': 'MALKIST', 'category': 'Crackers'}
    ]


def test_sku_recommendation_service_merges_graph_and_excel_without_duplicates(monkeypatch):
    service = SKURecommendationService()
    service.graph_repo = MagicMock()
    service.graph_repo.get_recommendations_for_distributor.return_value = [
        {'sku_name': 'MALKIST'}, {'sku_name': 'KOPIKO'}
    ]
    cursor = MagicMock()
    cursor.fetchall.return_value = [('KOPIKO',), ('BENG BENG',)]
    conn = MagicMock()
    conn.cursor.return_value = cursor
    monkeypatch.setattr('app.services.sku_recommendation_service.get_connection', lambda: conn)

    result = service.execute('D01', graph_limit=5, excel_limit=5)

    assert result['recommendations'] == ['MALKIST', 'KOPIKO', 'BENG BENG']
    cursor.execute.assert_called_once()
    cursor.close.assert_called_once()
    conn.close.assert_called_once()


def test_get_recommended_products_returns_list(monkeypatch):
    class FakeService:
        def execute(self, distributor_id, graph_limit=5, excel_limit=5):
            return {'recommendations': ['A', 'B']}
    monkeypatch.setattr('app.services.sku_recommendation_service.SKURecommendationService', FakeService)
    assert get_recommended_products('D01') == ['A', 'B']
