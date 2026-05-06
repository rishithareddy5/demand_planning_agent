from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.database import ensure_confirmed_demands_table
from app.services.send_demand_email_service import send_email, send_bulk_emails

from app.controllers.reply_validation_controller import router as validation_router

from view_data import get_all_replies


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_confirmed_demands_table()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.include_router(validation_router)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def home():
    return {
        "message": f"{settings.APP_NAME} is running",
        "version": settings.APP_VERSION,
    }


@app.get("/dashboard")
def dashboard(request: Request):
    print("Dashboard API called")

    rows = get_all_replies()

    print(f"Fetched {len(rows)} rows from database")

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "rows": rows,
        },
    )


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