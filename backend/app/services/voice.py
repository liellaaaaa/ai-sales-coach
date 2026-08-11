import base64
import binascii
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.xiaomimimo.com"
TOKEN_PLAN_BASE_URL = "https://token-plan-cn.xiaomimimo.com"
TTS_MAX_CHARS = 500
MAX_AUDIO_BASE64_LENGTH = 8 * 1024 * 1024
TTS_STYLE_PROMPT = "用自然、平稳、接近真人客服的语气朗读，语速适中。"


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

    async def synthesize(self, text: str) -> bytes:
        payload = {
            "model": settings.mimo_tts_model,
            "messages": [
                {"role": "user", "content": TTS_STYLE_PROMPT},
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
