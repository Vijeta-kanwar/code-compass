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
    embedding_batch_size: int = 50
    embedding_max_retries: int = 7
    embedding_batch_delay_seconds: float = 2.0

    #Repo settings
    clone_dir: str = "/tmp/codecompass"
    allowed_git_hosts: str = "github.com,gitlab.com"
    clone_timeout_seconds: int = 300
    max_repo_mb: int = 200
    max_file_bytes: int = 1_000_000      # skip minified bundles and vendored blobs

    @property
    def git_host_allowlist(self) -> set[str]:
        return {h.strip().lower() for h in self.allowed_git_hosts.split(",") if h.strip()}

@lru_cache
def get_settings() -> Settings:
    # Cached so the file is parsed once per process, and so tests can point at
    # a throwaway database by clearing the cache instead of patching os.environ.
    return Settings()