from fastapi import FastAPI
from contextlib import asynccontextmanager
import inngest.fast_api

from app.core.config import settings
from app.core.database import ensure_confirmed_demands_table
from app.services.send_demand_email_service import send_email, send_bulk_emails
from app.inngest_functions import inngest_client, inngest_functions

# ── Routers ───────────────────────────────────────────────────────────────────
from app.controllers.reply_validation_controller import router as validation_router
from app.controllers.postal_webhook_controller import router as webhook_router  # ← Fix: was never registered
from app.controllers.whatsapp_webhook_controller import router as whatsapp_router  # ← New: WhatsApp webhook router


# ── Lifespan: runs once on startup ────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_confirmed_demands_table()
    yield


# ── App init ──────────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# ── Register Inngest serve endpoint ───────────────────────────────────────────
# Inngest will call POST /api/inngest to execute functions
inngest.fast_api.serve(
    app,
    inngest_client,
    inngest_functions,
)

# ── Register routers ──────────────────────────────────────────────────────────
app.include_router(validation_router)
app.include_router(webhook_router)   # ← Fix: POST /webhook/reply is now live


# ── Base routes ───────────────────────────────────────────────────────────────
@app.get("/")
def home():
    return {
        "message": f"{settings.APP_NAME} is running",
        "version": settings.APP_VERSION,
    }


@app.get("/health")
def health_check():
    return {
        "status": "success",
        "message": "Application startup complete.",
    }


@app.get("/send-test")
def send_test():
    return send_email(
        to_email="demo@postal.local",
        subject="Test Email from Demand Planning Agent",
        body="Hello, this is a test email sent from FastAPI using Gmail SMTP.",
    )


@app.get("/send-bulk")
def send_bulk():
    distributors = [
        {"id": "D01", "email": "revanbejagam@gmail.com"},
        {"id": "D02", "email": "rishithareddyc2002@gmail.com"},
        {"id": "D03", "email": "Saherwardi.mustafa@gmail.com"},
        {"id": "D04", "email": "lingaphani21@gmail.com"},
        {"id": "D05", "email": "poojithak493@gmail.com"},
    ]
    return send_bulk_emails(distributors)

app.include_router(whatsapp_router)  # ← New: Register WhatsApp webhook router