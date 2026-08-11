import base64
import binascii
import json
import logging
from typing import AsyncGenerator

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.xiaomimimo.com"
TOKEN_PLAN_BASE_URL = "https://token-plan-cn.xiaomimimo.com"
TTS_MAX_CHARS = 500
MAX_AUDIO_BASE64_LENGTH = 8 * 1024 * 1024
TTS_STYLE_PROMPT = "用自然、平稳、接近真人客服的语气朗读，语速适中。"

# 场景模板 → TTS 风格指令映射
_TEMPLATE_STYLE_MAP: dict[str, str] = {
    "price-objection": "用强势、不容商量的语气说话，语速偏快，声音低沉有力，带着压迫感和不耐烦，像一个精明的采购经理在压价。",
    "delivery-risk": "用谨慎、质疑的语气说话，语速适中偏慢，声音沉稳但带着审视感，像一个资深供应链经理在核对细节。",
    "quality-proof": "用专业、严肃且略带质疑的语气说话，语速平稳，声音清晰有力，像一个品质总监在技术评审中追问。",
    "stalled-opportunity": "用客气但有距离感的语气说话，语速适中，声音平和，像一个忙碌的企业高管在推脱一个不太重要的会面。",
    "payment-followup": "用敷衍、心不在焉的语气说话，语速时快时慢，声音略显疲态，像一个总在找借口拖延的采购负责人。",
    "payment-quality-objection": "用不满且理直气壮的语气说话，语速偏快，声音带着质问感，像一个因为品质问题拒付货款的客户。",
    "payment-extension": "用强势但略带圆滑的语气说话，语速适中，声音低沉，像一个老练的财务总监在谈账期条件。",
}

# 客户画像 → 风格补充
_DIFFICULTY_STYLE: dict[str, str] = {
    "高压": "强势、有压迫感",
    "刁钻": "挑剔、善于追问细节",
}

_PERSONALITY_STYLE: dict[str, str] = {
    "压价型": "语速偏快，声音有攻击性",
    "谨慎型": "语速偏慢，声音沉稳审慎",
    "专业型": "声音清晰理性，逻辑性强",
    "敷衍型": "语速不均匀，声音漫不经心",
}

_DEFAULT_STYLE = "用自然、平稳、接近真实客户的语气说话，语速适中，声音平和自然。"


def get_tts_style(template_id: str = "", difficulty: str = "标准", personality: str = "谨慎型") -> str:
    """根据训练场景配置返回 TTS 自然语言风格指令。"""
    if template_id and template_id in _TEMPLATE_STYLE_MAP:
        return _TEMPLATE_STYLE_MAP[template_id]
    # 无精确模板匹配时，按客户画像动态拼接
    diff_part = _DIFFICULTY_STYLE.get(difficulty, "")
    pers_part = _PERSONALITY_STYLE.get(personality, "")
    if diff_part and pers_part:
        return f"用{diff_part}的语气说话，{pers_part}，像一个真实客户在对话。"
    if diff_part:
        return f"用{diff_part}的语气说话，像一个真实客户在对话。"
    if pers_part:
        return f"说话时{pers_part}，像一个真实客户在对话。"
    return _DEFAULT_STYLE


class VoiceError(Exception):
    """上游语音服务调用失败（非超时）。"""


class VoiceTimeoutError(VoiceError):
    """上游语音服务响应超时。"""


def is_wav_base64(audio_base64: str) -> bool:
    try:
        head = base64.b64decode(audio_base64[:16], validate=True)
    except (binascii.Error, ValueError):
        return False
    return head.startswith(b"RIFF") and head[8:12] == b"WAVE"


class VoiceClient:
    @property
    def configured(self) -> bool:
        return bool(settings.mimo_api_key)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {settings.mimo_api_key}",
            "Content-Type": "application/json",
        }

    def _url(self) -> str:
        base_url = (settings.mimo_base_url or "").strip().rstrip("/")
        if not base_url or base_url == DEFAULT_BASE_URL:
            base_url = TOKEN_PLAN_BASE_URL if (settings.mimo_api_key or "").startswith("tp-") else DEFAULT_BASE_URL
        return f"{base_url}/v1/chat/completions"

    async def _post(self, payload: dict) -> dict:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=15.0)) as client:
                response = await client.post(self._url(), json=payload, headers=self._headers())
                response.raise_for_status()
                try:
                    body = response.json()
                except ValueError as exc:
                    raise VoiceError("语音服务返回了无法解析的响应") from exc
                if not isinstance(body, dict):
                    raise VoiceError("语音服务响应格式异常")
                return body
        except httpx.TimeoutException as exc:
            logger.warning("MiMo 语音服务响应超时：%s", exc)
            raise VoiceTimeoutError(str(exc)) from exc
        except httpx.HTTPError as exc:
            logger.warning("MiMo 语音服务调用失败：%s", exc)
            raise VoiceError(str(exc)) from exc

    async def transcribe(self, audio_base64: str, mime_type: str) -> str:
        payload = {
            "model": settings.mimo_asr_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {"data": f"data:{mime_type};base64,{audio_base64}"},
                        }
                    ],
                }
            ],
            "asr_options": {"language": "auto"},
        }
        body = await self._post(payload)
        choices = body.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        return (message.get("content") or "").strip()

    async def synthesize(self, text: str, style_prompt: str = "") -> bytes:
        payload = {
            "model": settings.mimo_tts_model,
            "messages": [
                {"role": "user", "content": style_prompt or TTS_STYLE_PROMPT},
                {"role": "assistant", "content": text},
            ],
            "audio": {"format": "wav", "voice": settings.mimo_tts_voice or "苏打"},
        }
        body = await self._post(payload)
        choices = body.get("choices") or []
        if not choices:
            raise VoiceError("TTS 响应缺少音频数据")
        audio = (choices[0].get("message") or {}).get("audio") or {}
        data = audio.get("data") or ""
        if not data:
            raise VoiceError("TTS 响应缺少音频数据")
        try:
            return base64.b64decode(data)
        except (binascii.Error, ValueError) as exc:
            raise VoiceError("TTS 音频数据解码失败") from exc

    async def synthesize_stream(self, text: str, style_prompt: str = "") -> AsyncGenerator[bytes, None]:
        """流式 TTS 合成，逐块 yield PCM16 原始字节。"""
        payload = {
            "model": settings.mimo_tts_model,
            "messages": [
                {"role": "user", "content": style_prompt or TTS_STYLE_PROMPT},
                {"role": "assistant", "content": text},
            ],
            "audio": {"format": "pcm16", "voice": settings.mimo_tts_voice or "苏打"},
            "stream": True,
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=15.0)) as client:
                async with client.stream("POST", self._url(), json=payload, headers=self._headers()) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:]
                        if data.strip() == "[DONE]":
                            break
                        try:
                            obj = json.loads(data)
                            choices = obj.get("choices") or []
                            if choices:
                                delta = choices[0].get("delta") or {}
                                audio = delta.get("audio")
                                if audio and isinstance(audio, dict):
                                    pcm_b64 = audio.get("data")
                                    if pcm_b64:
                                        yield base64.b64decode(pcm_b64)
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
        except httpx.TimeoutException as exc:
            logger.warning("MiMo TTS 流式响应超时：%s", exc)
            raise VoiceTimeoutError(str(exc)) from exc
        except httpx.HTTPError as exc:
            logger.warning("MiMo TTS 流式调用失败：%s", exc)
            raise VoiceError(str(exc)) from exc
