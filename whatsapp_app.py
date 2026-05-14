#Isolated integ testing
from fastapi import FastAPI

from app.controllers.whatsapp_webhook_controller import router as whatsapp_router
from app.data.sku_data import load_sku_data

load_sku_data(
    primary_sales_file="sample_data/Primary_Sales.xlsx",
    recommended_products_file="sample_data/30_Recommended_New_Products.xlsx"
)

app = FastAPI()

app.include_router(whatsapp_router)


@app.get("/")
async def root():

    return {
        "message": "WhatsApp Integration Running"
    }