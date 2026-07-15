"""Configuration, validated at boot. Fail loudly, never silently."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # PINNED, never 'mistral-large-latest': an alias silently re-pointing mid-assessment is
    # both a dead demo and an uncontrolled eval variable.
    mistral_model: str = "mistral-large-2512"
    mistral_api_key: str | None = None

    # The free tier does not publish its rate limit -- Mistral's own docs tell you to read
    # it off your admin console. So this is an env var, observed and dated, never a number
    # hardcoded from a blog post. The design honours whatever Retry-After the server sends.
    max_concurrent_requests: int = 1
    requests_per_second: float = 1.0

    # Uploads only. Unset is a supported, tested state: the committed corpus and all six
    # demo questions work with zero network calls.
    pinecone_api_key: str | None = None
    pinecone_index: str = "eda-kb"

    index_dir: str = "index"
    log_level: str = "INFO"

    @property
    def generation_available(self) -> bool:
        return bool(self.mistral_api_key)


settings = Settings()
