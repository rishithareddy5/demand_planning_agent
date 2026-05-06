from fastapi import APIRouter
from app.services.load_new_products_to_graph_service import LoadNewProductsToGraphService

router = APIRouter(prefix="/graph", tags=["Graph"])


@router.post("/load-new-products")
def load_new_products():
    service = LoadNewProductsToGraphService()
    return service.execute()