"""FastAPI 依赖注入：Client / Service 一律走 Depends，便于测试替换。"""
from __future__ import annotations

from functools import lru_cache

from app.services.llm import LLMClient
from app.services.knowledge_service import DOCUMENT_TAG_PRESETS  # noqa: F401  兼容旧导入
from app.services.training_service import TrainingService
from app.services.voice import VoiceClient


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    return LLMClient()


@lru_cache(maxsize=1)
def get_voice_client() -> VoiceClient:
    return VoiceClient()


def get_training_service() -> TrainingService:
    return TrainingService(llm=get_llm_client(), voice=get_voice_client())


def reset_client_cache() -> None:
    """测试用：清掉单例缓存，便于注入 Fake。"""
    get_llm_client.cache_clear()
    get_voice_client.cache_clear()
