from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    # =========================
    # App Info
    # =========================
    APP_NAME: str = "Demand Planning Agent"
    APP_VERSION: str = "1.0.0"

    # =========================
    # PostgreSQL
    # =========================
    POSTGRES_HOST: str
    POSTGRES_PORT: int
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str

    # =========================
    # FalkorDB
    # =========================
    FALKOR_HOST: str
    FALKOR_PORT: int
    FALKOR_GRAPH: str

    # =========================
    # Gmail SMTP (sending emails)
    # =========================
    EMAIL_ADDRESS: str        # e.g. bejagamrevan@gmail.com
    EMAIL_APP_PASSWORD: str   # Gmail App Password (not account password)
    SMTP_SERVER: str = "smtp.gmail.com"
    SMTP_PORT: int = 465

    # =========================
    # Gmail IMAP (reading replies)
    # =========================
    IMAP_SERVER: str = "imap.gmail.com"
    IMAP_PORT: int = 993

    # =========================
    # RedPanda
    # =========================
    REDPANDA_BROKER: str = "localhost:9092"

    # =========================
    # Temporal
    # =========================
    TEMPORAL_HOST: str = "localhost:7233"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()