import base64
import hashlib
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import SessionLocal
from app.models import LLMConfig


DEFAULT_PROVIDER = "deepseek"
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL_NAME = "DeepSeek V4 Flash"
DEFAULT_MODEL_ID = "deepseek-v4-flash"
API_KEY_PREFIX = "enc:"


@dataclass
class EffectiveLLMConfig:
    provider: str
    api_key: str
    base_url: str
    group_id: str
    model_name: str
    model_id: str

    @property
    def configured(self) -> bool:
        return bool(self.api_key and (self.base_url or self.group_id))

    @property
    def mode(self) -> str:
        return "llm" if self.configured else "mock"


def mask_api_key(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:4]}****{api_key[-4:]}"


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.jwt_secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _encrypt_api_key(api_key: str) -> str:
    return f"{API_KEY_PREFIX}{_fernet().encrypt(api_key.encode('utf-8')).decode('utf-8')}"


def _decrypt_api_key(value: str) -> str:
    if not value:
        return ""
    if not value.startswith(API_KEY_PREFIX):
        return value
    try:
        return _fernet().decrypt(value[len(API_KEY_PREFIX) :].encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return ""


def normalize_base_url(base_url: str | None) -> str:
    value = (base_url or DEFAULT_BASE_URL).strip().rstrip("/") or DEFAULT_BASE_URL
    allowed = {DEFAULT_BASE_URL, "https://api.minimaxi.com/v1", "https://api.deepseek.com/v1"}
    if value not in allowed:
        raise ValueError(f"only {allowed} are supported")
    return value


def config_to_public(config: EffectiveLLMConfig) -> dict:
    return {
        "provider": config.provider,
        "base_url": config.base_url,
        "model_name": config.model_name,
        "model_id": config.model_id,
        "has_api_key": bool(config.api_key),
        "api_key_masked": mask_api_key(config.api_key),
        "llm_configured": config.configured,
        "llm_mode": config.mode,
    }


def get_effective_llm_config(db: Session | None = None) -> EffectiveLLMConfig:
    if db is None:
        local_db = SessionLocal()
        try:
            return get_effective_llm_config(local_db)
        finally:
            local_db.close()

    row = db.get(LLMConfig, 1)
    env_model_id = settings.deepseek_model if settings.deepseek_api_key else ""

    # Database takes priority, but fall back to env vars when DB values are empty
    db_api_key = _decrypt_api_key(row.api_key) if row else ""
    api_key = db_api_key or settings.deepseek_api_key

    db_base_url = (row.base_url if row else "").strip() if row else ""
    raw_base_url = db_base_url or settings.deepseek_base_url
    try:
        base_url = normalize_base_url(raw_base_url)
    except ValueError:
        base_url = DEFAULT_BASE_URL

    return EffectiveLLMConfig(
        provider=(row.provider if row else "") or DEFAULT_PROVIDER,
        api_key=api_key,
        base_url=base_url,
        group_id=settings.deepseek_group_id,
        model_name=(row.model_name if row else "") or DEFAULT_MODEL_NAME,
        model_id=(row.model_id if row else "") or env_model_id or DEFAULT_MODEL_ID,
    )


def save_llm_config(db: Session, *, api_key: str | None, clear_api_key: bool, base_url: str | None, model_name: str | None, model_id: str | None) -> EffectiveLLMConfig:
    row = db.get(LLMConfig, 1)
    if not row:
        row = LLMConfig(id=1)
        db.add(row)

    if clear_api_key:
        row.api_key = ""
    elif api_key is not None and api_key.strip():
        row.api_key = _encrypt_api_key(api_key.strip())

    if base_url is not None:
        row.base_url = normalize_base_url(base_url)
    if model_name is not None:
        row.model_name = model_name.strip() or DEFAULT_MODEL_NAME
    if model_id is not None:
        row.model_id = model_id.strip() or DEFAULT_MODEL_ID

    db.commit()
    db.refresh(row)
    return get_effective_llm_config(db)
