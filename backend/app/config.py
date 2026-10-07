from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SALES_COACH_")

    app_name: str = "AI 销售陪练 MVP"
    database_url: str = "postgresql+psycopg2://sales_coach:sales_coach@localhost:5432/sales_coach"
    jwt_secret: str = "change-me-in-intranet"
    jwt_algorithm: str = "HS256"
    # API Key 加密专用密钥；留空时回退 jwt_secret 派生（兼容旧密文）
    secret_key: str = ""
    deepseek_api_key: str = ""
    deepseek_base_url: str = ""
    deepseek_group_id: str = ""
    deepseek_model: str = "deepseek-v4-flash"
    mimo_api_key: str = ""
    mimo_base_url: str = "https://api.xiaomimimo.com"
    mimo_asr_model: str = "mimo-v2.5-asr"
    mimo_tts_model: str = "mimo-v2.5-tts"
    mimo_tts_voice: str = "苏打"


settings = Settings()


def validate_settings() -> list[str]:
    """启动自检：返回告警列表（空表示健康）。"""
    warnings: list[str] = []
    using_default_secret = settings.jwt_secret.startswith("change-me")
    if using_default_secret:
        warnings.append(
            "SALES_COACH_JWT_SECRET 仍为默认值"
            + ("，且未配置 SALES_COACH_SECRET_KEY" if not settings.secret_key else "")
        )
    if "://" not in settings.database_url:
        warnings.append("SALES_COACH_DATABASE_URL 格式异常")
    return warnings
