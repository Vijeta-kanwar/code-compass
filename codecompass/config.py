from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    
    database_url: str
    google_api_key: str

    llm_model: str = "gemini-2.5-flash"
    embedding_model: str = "gemini-embedding-001"
    # 768 rather than the model's native 3072 — see the note below; this is a
    # hard constraint from pgvector, not a cost optimisation.
    embedding_dimensions: int = 768
    log_level: str = "INFO"

@lru_cache
def get_settings() -> Settings:
    # Cached so the file is parsed once per process, and so tests can point at
    # a throwaway database by clearing the cache instead of patching os.environ.
    return Settings()