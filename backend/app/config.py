from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent

class Settings(BaseSettings):
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    DEBUG: bool = True
    DB_PATH: str = str(BASE_DIR / "abenzo.db")
    DATABASE_URL: str = ""  # PostgreSQL connection string (Neon). When set, overrides DB_PATH.
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_MODEL: str = "qwen2.5:3b"
    OLLAMA_TIMEOUT_SECONDS: int = 60

    @property
    def is_postgres(self) -> bool:
        """Returns True when a PostgreSQL DATABASE_URL is configured."""
        url = (self.DATABASE_URL or "").strip().lower()
        return url.startswith("postgres://") or url.startswith("postgresql://")

    # Hosted AI Provider Configuration (OpenAI-compatible)
    AI_PROVIDER: str = "ollama"  # "ollama" (default local) or "openai_compatible"
    AI_BASE_URL: str = ""        # e.g. "https://api.groq.com/openai/v1"
    AI_API_KEY: str = ""         # Provider API Key (never printed or exposed to frontend)
    AI_MODEL: str = ""           # e.g. "llama-3.1-8b-instant"
    AI_TIMEOUT_SECONDS: int = 30
    
    # Meta Instagram Configuration
    META_APP_ID: str = ""
    META_APP_SECRET: str = ""
    META_ACCESS_TOKEN: str = ""
    META_VERIFY_TOKEN: str = "abenzo_verify_token_sample"
    META_PAGE_ID: str = ""

    # Instagram Developer App / Login for Business Credentials
    INSTAGRAM_ACCESS_TOKEN: str = ""
    INSTAGRAM_APP_ID: str = ""
    INSTAGRAM_APP_SECRET: str = ""

    @property
    def effective_instagram_token(self) -> str:
        return (self.INSTAGRAM_ACCESS_TOKEN or self.META_ACCESS_TOKEN or "").strip()

    @property
    def effective_instagram_app_id(self) -> str:
        return (self.INSTAGRAM_APP_ID or self.META_APP_ID or "").strip()

    @property
    def effective_instagram_app_secret(self) -> str:
        return (self.INSTAGRAM_APP_SECRET or self.META_APP_SECRET or "").strip()

    # CORS configuration
    CORS_ORIGINS: str = ""

    @property
    def allowed_cors_origins(self) -> list[str]:
        base_origins = [
            "https://abenzo-ai.vercel.app",
            "https://abenzo.vercel.app",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
        if not self.CORS_ORIGINS.strip():
            return base_origins
        origins = [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]
        for b in base_origins:
            if b not in origins:
                origins.append(b)
        return origins

    model_config = SettingsConfigDict(
        env_file=(str(ROOT_DIR / ".env"), str(BASE_DIR / ".env"), ".env"),
        extra="ignore"
    )

settings = Settings()
