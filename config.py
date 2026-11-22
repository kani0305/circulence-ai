import os
from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "CircularIQ"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api"
    SECRET_KEY: str = "circulariq-super-secret-jwt-key-2026-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # Database
    DATABASE_URL: str = "sqlite:///./circulariq.db"
    
    # Vector DB & Storage
    CHROMA_PERSIST_DIRECTORY: str = "./chroma_db"
    UPLOAD_DIRECTORY: str = "./uploads"

    # Nexus API Configuration (Strictly modular)
    NEXUS_API_BASE_URL: str = ""
    NEXUS_API_KEY: str = ""
    NEXUS_API_TOKEN: str = ""

    # AI / LLM Configuration
    LLM_PROVIDER: str = "local_rule_engine"  # "gemini", "openai", "local_rule_engine"
    GEMINI_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    LLM_MODEL: str = "gemini-1.5-flash"

    # Deadline notification intervals in days
    REMINDER_INTERVALS_DAYS: list[int] = [7, 3, 1, 0]

    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()

os.makedirs(settings.UPLOAD_DIRECTORY, exist_ok=True)
os.makedirs(settings.CHROMA_PERSIST_DIRECTORY, exist_ok=True)
