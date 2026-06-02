from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SHINKAI_", env_file=".env")

    env: str = "development"
    auth_required: bool = False
    admin_token: str | None = None
    subscriber_tokens: list[str] = []
    # Shared HMAC secret used to verify JWTs minted by the web layer's
    # NextAuth callback. The same secret must be present in the web env
    # (NEXTAUTH_SECRET) and on the API service. When empty, only the
    # legacy admin_token path is accepted.
    session_jwt_secret: str | None = None
    session_jwt_algorithm: str = "HS256"
    # Comma-separated whitelist of owner emails / OAuth identities. Anyone
    # signing in with an email on this list is granted the admin role;
    # everyone else (including unauthenticated viewers) is read-only.
    owner_emails: list[str] = []
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://localhost:3100",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002",
        "http://127.0.0.1:3100",
    ]
    cors_origin_regex: str | None = r"http://(localhost|127\.0\.0\.1):\d+"
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"
    tavily_api_key: str | None = None
    tavily_base_url: str = "https://api.tavily.com"
    persistence_enabled: bool = True
    database_url: str | None = None
    persistence_json_fallback: bool = True
    state_path: str = ".shinkai/state.json"
    published_dossier_top_n: int = 12
    harness_max_loops_divisor: int = 20


settings = Settings()
