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

    # Auth gates the UPLOAD surface only. The demo corpus is public and stays public: an
    # assessment demo behind a login is a demo nobody sees.
    #
    # A hash, never a password, and both from the environment -- this repo is public. There
    # is no user table because there is one account; a database of one row would be
    # architecture theatre. Generate with:
    #   python -c "import bcrypt;print(bcrypt.hashpw(b'PW', bcrypt.gensalt(12)).decode())"
    auth_email: str | None = None
    auth_password_hash: str | None = None
    session_secret: str | None = None

    # Bounds on the upload surface. These are not arbitrary -- see api/uploads.py. The box
    # has 512 MB and the baseline already uses ~435 MB, so an unbounded upload is an OOM,
    # and an OOM is a dead URL for the reviewer clicking the public demo.
    max_upload_mb: int = 20
    max_upload_pages: int = 60
    max_inmemory_kbs: int = 3

    index_dir: str = "index"
    log_level: str = "INFO"

    @property
    def generation_available(self) -> bool:
        return bool(self.mistral_api_key)

    @property
    def auth_available(self) -> bool:
        return bool(self.auth_email and self.auth_password_hash and self.session_secret)

    @property
    def uploads_persist(self) -> bool:
        """Do uploaded KBs survive a restart? Only if they live off-box."""
        return bool(self.pinecone_api_key)


settings = Settings()
