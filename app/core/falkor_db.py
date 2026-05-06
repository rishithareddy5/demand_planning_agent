from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from falkordb import FalkorDB


class FalkorSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False
    )

    FALKORDB_HOST: str = Field(default="localhost", validation_alias="falkor_host")
    FALKORDB_PORT: int = Field(default=6379, validation_alias="falkor_port")
    FALKORDB_GRAPH_NAME: str = Field(default="demand_graph", validation_alias="falkor_graph")


settings = FalkorSettings()

db = FalkorDB(
    host=settings.FALKORDB_HOST,
    port=settings.FALKORDB_PORT
)

graph = db.select_graph(settings.FALKORDB_GRAPH_NAME)