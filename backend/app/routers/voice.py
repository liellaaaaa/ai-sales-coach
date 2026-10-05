import logging

from fastapi import APIRouter, Depends, HTTPException, Response

from app.models import User
from app.schemas import VoiceSpeechIn, VoiceTranscribeIn
from app.services.auth import current_user
from app.services.voice import (
    MAX_AUDIO_BASE64_LENGTH,
    TTS_MAX_CHARS,
    VoiceClient,
    VoiceError,
    VoiceTimeoutError,
    get_speaker_voice,
    get_tts_style,
    is_wav_base64,
    normalize_speaker,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])


def _require_configured(client: VoiceClient):
    if not client.configured:
        raise HTTPException(status_code=503, detail="语音功能未启用，请先配置 SALES_COACH_MIMO_API_KEY")


@router.post("/transcribe")
async def transcribe(payload: VoiceTranscribeIn, _: User = Depends(current_user)):
    client = VoiceClient()
    _require_configured(client)
    if len(payload.audio_base64) > MAX_AUDIO_BASE64_LENGTH:
        raise HTTPException(status_code=413, detail="音频过大，请录制 4 分钟以内")
    if payload.mime_type != "audio/wav" or not is_wav_base64(payload.audio_base64):
        raise HTTPException(status_code=400, detail="仅支持 wav 格式音频")
    try:
        text = await client.transcribe(payload.audio_base64, payload.mime_type)
    except VoiceTimeoutError:
        raise HTTPException(status_code=504, detail="语音服务响应超时，请稍后重试")
    except VoiceError:
        raise HTTPException(status_code=502, detail="语音识别失败，请稍后重试")
    return {"text": text}


@router.post("/speech")
async def synthesize(payload: VoiceSpeechIn, _: User = Depends(current_user)):
    speaker = normalize_speaker(payload.speaker)
    client = VoiceClient(voice=get_speaker_voice(speaker), style_prompt=get_tts_style(speaker=speaker))
    _require_configured(client)
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="文本不能为空")
    if len(text) > TTS_MAX_CHARS:
        logger.warning("TTS 文本超过 %s 字，自动截断（原长度 %s）", TTS_MAX_CHARS, len(text))
        text = text[:TTS_MAX_CHARS]
    try:
        audio = await client.synthesize(text)
    except VoiceTimeoutError:
        raise HTTPException(status_code=504, detail="语音服务响应超时，请稍后重试")
    except VoiceError:
        raise HTTPException(status_code=502, detail="语音合成失败，请稍后重试")
    return Response(content=audio, media_type="audio/wav")
