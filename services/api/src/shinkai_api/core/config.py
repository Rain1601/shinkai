from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SHINKAI_", env_file=".env")

    env: str = "development"
    auth_required: bool = False
    admin_token: str | None = None
    subscriber_tokens: list[str] = []
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
    persistence_enabled: bool = True
    database_url: str | None = None
    persistence_json_fallback: bool = True
    state_path: str = ".shinkai/state.json"
    published_dossier_top_n: int = 12
    harness_max_loops_divisor: int = 20


settings = Settings()
