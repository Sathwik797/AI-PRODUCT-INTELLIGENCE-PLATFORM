import json
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Product Intelligence Platform"
    app_version: str = "1.0.0"
    debug: bool = False

    # Database: Supports single connection string (e.g., Render/Railway DATABASE_URL)
    # or separate credentials (DB_HOST, DB_USER, etc.)
    database_url: str | None = None
    db_host: str = "localhost"
    db_port: int = 3306
    db_name: str = "ai_product_db"
    db_user: str = "root"
    db_password: str = ""

    db_pool_size: int = 10
    db_max_overflow: int = 10
    db_pool_recycle: int = 1800
    db_pool_timeout: int = 30

    cors_origins: str | list[str] = ["http://localhost:3000", "http://localhost:5173"]

    @field_validator("cors_origins", mode="after")
    @classmethod
    def assemble_cors_origins(cls, v):
        if isinstance(v, str):
            v_trimmed = v.strip()
            if v_trimmed == "*":
                return ["*"]
            if v_trimmed.startswith("[") and v_trimmed.endswith("]"):
                try:
                    return json.loads(v_trimmed)
                except Exception:
                    pass
            return [i.strip() for i in v_trimmed.split(",") if i.strip()]
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
