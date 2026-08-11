from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "AI 销售陪练 MVP"
    database_url: str = "postgresql+psycopg2://sales_coach:sales_coach@localhost:5432/sales_coach"
    jwt_secret: str = "change-me-in-intranet"
    jwt_algorithm: str = "HS256"
    deepseek_api_key: str = ""
    deepseek_base_url: str = ""
    deepseek_group_id: str = ""
    deepseek_model: str = "deepseek-v4-flash"
    mimo_api_key: str = ""
    mimo_base_url: str = "https://api.xiaomimimo.com"
    mimo_asr_model: str = "mimo-v2.5-asr"
    mimo_tts_model: str = "mimo-v2.5-tts"
    mimo_tts_voice: str = "苏打"

    class Config:
        env_file = ".env"
        env_prefix = "SALES_COACH_"


settings = Settings()
