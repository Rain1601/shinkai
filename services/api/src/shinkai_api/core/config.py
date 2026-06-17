import os

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
    # Legacy Google Custom Search JSON API — closed to new GCP projects;
    # kept for grandfathered customers.
    google_search_api_key: str | None = None
    google_search_engine_id: str | None = None
    # Vertex AI Grounding (Gemini + google_search tool) — the supported
    # successor to CSE.
    google_cloud_project: str | None = None
    google_cloud_location: str = "us-central1"
    google_application_credentials: str | None = None
    vertex_model: str = "gemini-2.5-flash"
    # Which web-search backend the WebSearchTool defaults to. "auto" lets
    # market-utils pick the first configured one in its preference order
    # (vertex_grounding → tavily → google → duckduckgo).
    web_search_strategy: str = "auto"
    persistence_enabled: bool = True
    database_url: str | None = None
    persistence_json_fallback: bool = True
    state_path: str = ".shinkai/state.json"
    published_dossier_top_n: int = 12
    harness_max_loops_divisor: int = 20


settings = Settings()


def bridge_env_to_market_utils() -> None:
    """Mirror SHINKAI-prefixed search settings to market-utils env names."""

    if settings.tavily_api_key and not os.environ.get("TAVILY_API_KEY"):
        os.environ["TAVILY_API_KEY"] = settings.tavily_api_key
    if settings.tavily_base_url:
        os.environ.setdefault("TAVILY_BASE_URL", settings.tavily_base_url)

    google_key = settings.google_search_api_key or os.environ.get(
        "SHINKAI_GOOGLE_SEARCH_API_KEY"
    )
    google_cx = settings.google_search_engine_id or os.environ.get(
        "SHINKAI_GOOGLE_SEARCH_ENGINE_ID"
    )
    if google_key and not os.environ.get("GOOGLE_SEARCH_API_KEY"):
        os.environ["GOOGLE_SEARCH_API_KEY"] = google_key
    if google_cx and not os.environ.get("GOOGLE_SEARCH_ENGINE_ID"):
        os.environ["GOOGLE_SEARCH_ENGINE_ID"] = google_cx

    # Vertex Grounding — project + ADC credentials + model + region
    if settings.google_cloud_project and not os.environ.get("GOOGLE_CLOUD_PROJECT"):
        os.environ["GOOGLE_CLOUD_PROJECT"] = settings.google_cloud_project
    if settings.google_cloud_location:
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", settings.google_cloud_location)
    if settings.google_application_credentials and not os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS"
    ):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = (
            settings.google_application_credentials
        )
    if settings.vertex_model:
        os.environ.setdefault("MARKET_UTILS_VERTEX_MODEL", settings.vertex_model)
