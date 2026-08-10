import base64
import binascii
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.xiaomimimo.com"
TTS_MAX_CHARS = 500
MAX_AUDIO_BASE64_LENGTH = 8 * 1024 * 1024
TTS_STYLE_PROMPT = "用自然、平稳、接近真人客服的语气朗读，语速适中。"


class VoiceError(Exception):
    """上游语音服务调用失败（非超时）。"""


class VoiceTimeoutError(Exception):
    """上游语音服务响应超时。"""


def is_wav_base64(audio_base64: str) -> bool:
    try:
        head = base64.b64decode(audio_base64[:8], validate=True)
    except (binascii.Error, ValueError):
        return False
    return head.startswith(b"RIFF")


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
        base_url = (settings.mimo_base_url or DEFAULT_BASE_URL).rstrip("/")
        return f"{base_url}/v1/chat/completions"

    async def _post(self, payload: dict) -> dict:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=15.0)) as client:
                response = await client.post(self._url(), json=payload, headers=self._headers())
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException as exc:
            raise VoiceTimeoutError(str(exc)) from exc
        except httpx.HTTPError as exc:
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
            "audio": {"format": "wav", "voice": "mimo_default"},
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
