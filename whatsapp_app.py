from fastapi import FastAPI

from app.controllers.whatsapp_webhook_controller import router as whatsapp_router

app = FastAPI()

app.include_router(whatsapp_router)


@app.get("/")
async def root():

    return {
        "message": "WhatsApp Integration Running"
    }