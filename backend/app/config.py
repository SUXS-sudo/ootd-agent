from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    app_name: str = "衣序 OOTD API"
    environment: str = "development"
    database_url: str = "mysql+pymysql://ootd:ootd@localhost:3306/ootd?charset=utf8mb4"
    redis_url: str = "redis://localhost:6379/0"
    preference_cache_ttl_seconds: int = 1800
    styling_session_ttl_seconds: int = 7200
    langgraph_checkpoint_url: str = "mysql://ootd:ootd@localhost:3306/ootd_checkpoints?charset=utf8mb4"
    storage_backend: str = "local"
    storage_bucket: str = "ootd-private"
    storage_endpoint_url: str | None = None
    storage_access_key_id: str | None = None
    storage_secret_access_key: str | None = None
    storage_region: str = "auto"
    storage_upload_url_ttl_seconds: int = 300
    storage_pending_ttl_seconds: int = 3600
    storage_reconcile_interval_seconds: int = 900
    storage_read_url_ttl_seconds: int = 600
    storage_max_image_bytes: int = 12 * 1024 * 1024
    storage_delete_grace_seconds: int = 7 * 24 * 3600
    # LLM —— 任意 OpenAI 兼容接口（DeepSeek / GLM / OpenAI）
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.deepseek.com/v1"
    openai_model: str = "deepseek-chat"
    openai_planning_model: str | None = None
    openai_ranking_timeout_seconds: float = 8.0
    openai_vision_model: str | None = None
    openai_vision_base_url: str | None = None
    openai_vision_api_key: str | None = None
    openai_image_model: str = "gpt-image-2"
    openai_image_size: str = "1024x1536"
    openai_image_endpoint: str = "/chat/completions"
    openai_image_base_url: str | None = None
    openai_image_api_key: str | None = None
    proactive_scan_minutes: int = 15
    reminder_quiet_hours: str = "22:00-07:30"
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    demo_user_id: str = "u_1001"
    seed_demo_data: bool = True
    auth_shared_secret: str = "development-only-change-me"
    frontend_url: str = "http://localhost:3000"
    microsoft_client_id: str | None = None
    microsoft_client_secret: str | None = None
    microsoft_tenant: str = "common"
    microsoft_redirect_uri: str = "http://localhost:8000/api/v1/integrations/outlook/callback"
    photo_retention_hours: int = 0
    # One canonical configuration file, independent of the process working directory.
    model_config = SettingsConfigDict(env_file=BACKEND_DIR.parent / ".env", extra="ignore")

settings = Settings()

def should_seed_demo_data() -> bool:
    """Demo content is a local-development aid and must never enter production."""
    return settings.environment in {"development", "test"} and settings.seed_demo_data
