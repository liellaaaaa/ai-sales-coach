# 语音识别与输出（ASR/TTS）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在客户情景陪练对话中加入小米 MiMo 语音输入（ASR）与语音输出（TTS），点击录音自动发送、客户回复自动朗读可重听，未配 Key 时完全降级为纯文字。

**Architecture:** 后端代理模式——新增 `services/voice.py`（VoiceClient）与 `routers/voice.py` 两个端点，API Key 只存 `.env`；前端新增零 React 依赖的引擎模块 `audio.js` 与 UI 组件 `voice.jsx`，`App.jsx` 只做接线。验证沿用项目现有方式：后端 `python -m app.smoke_test`（脚本式断言 + TestClient + 猴子补丁），前端 `npm run build`。

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, httpx（后端）；React 18, Vite, MediaRecorder, OfflineAudioContext（前端）；小米 MiMo OpenAI 兼容 API（`https://api.xiaomimimo.com/v1/chat/completions`，模型 `mimo-v2.5-asr` / `mimo-v2.5-tts`）。

**设计文档：** `docs/superpowers/specs/2026-08-10-voice-asr-tts-design.md`

---

## 背景速览（执行者必读）

- 后端验证方式不是 pytest，而是 `cd backend && .\.venv\Scripts\python.exe -m app.smoke_test`。smoke 脚本用临时 sqlite 库、`TestClient(app)`、猴子补丁模拟外部服务（参考 `smoke_test.py` 里 `LLMClient.test_connection` 的补丁写法）。所有后端断言都加进这个脚本。
- 前端没有测试框架，验证靠 `npm run build` + 手工 E2E。
- 鉴权用 `app.services.auth.current_user`（JWT Bearer），语音端点与 `/training/*` 完全一致。
- `settings` 是全局单例，smoke 里可直接改字段（如 `settings.mimo_api_key = "x"`），用完必须还原。
- 提交信息风格：`feat: 中文描述`、`fix: 中文描述`。

---

## File Map

- 修改 `backend/app/config.py` — 新增 4 个 `mimo_*` 配置
- 新建 `backend/app/services/voice.py` — `VoiceClient`、`is_wav_base64`、异常类、常量
- 修改 `backend/app/schemas.py` — `MessageOut` 加 `id`；新增 `VoiceTranscribeIn` / `VoiceSpeechIn`
- 修改 `backend/app/routers/training.py` — 显式构造 `MessageOut` 处补 `id`
- 新建 `backend/app/routers/voice.py` — `/voice/transcribe`、`/voice/speech`
- 修改 `backend/app/main.py` — 挂载 voice 路由；`/api/health` 加 `voice_configured`
- 修改 `backend/app/smoke_test.py` — 全部语音回归断言
- 修改 `.env.example` — MiMo 占位配置
- 修改 `frontend/src/api.js` — 新增 `apiAudio()`
- 新建 `frontend/src/audio.js` — `AudioRecorder` / `AudioPlayer` / WAV 编码
- 新建 `frontend/src/voice.jsx` — `MicButton` / `PlayButton` / `AutoReadToggle`
- 修改 `frontend/src/App.jsx` — Chat 接线（send 重构、播放状态、UI 挂载）
- 修改 `frontend/src/styles.css` — 语音相关样式

---

### Task 1: 后端配置 + VoiceClient 服务 + health 字段

**Files:**
- Modify: `backend/app/config.py`
- Create: `backend/app/services/voice.py`
- Modify: `backend/app/main.py`
- Test: `backend/app/smoke_test.py`

- [ ] **Step 1: 先在 smoke_test.py 写失败断言**

`backend/app/smoke_test.py` 顶部 import 区（`import os` 附近）加：

```python
import base64
```

顶部 `from app.services.llm import ...` 一行之后加：

```python
from app.services.voice import VoiceClient, is_wav_base64
```

在 `run()` 函数里现有 health 断言块（`assert health_body["llm_mode"] == "mock"` 之后）加：

```python
    assert health_body["voice_configured"] is False
    assert VoiceClient().configured is False
    assert is_wav_base64(base64.b64encode(b"RIFF\x24\x08\x00\x00WAVEfmt ").decode("ascii")) is True
    assert is_wav_base64(base64.b64encode(b"OggS not wav at all").decode("ascii")) is False
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .\.venv\Scripts\python.exe -m app.smoke_test`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.services.voice'` 或 health 断言失败）

- [ ] **Step 3: 实现配置**

`backend/app/config.py` 的 `Settings` 类中，`deepseek_model` 字段后新增：

```python
    mimo_api_key: str = ""
    mimo_base_url: str = "https://api.xiaomimimo.com"
    mimo_asr_model: str = "mimo-v2.5-asr"
    mimo_tts_model: str = "mimo-v2.5-tts"
```

- [ ] **Step 4: 实现 `backend/app/services/voice.py`**

```python
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
```

- [ ] **Step 5: 修改 `backend/app/main.py`**

import 区加：

```python
from app.services.voice import VoiceClient
```

`health()` 返回值加字段：

```python
@app.get("/api/health")
def health():
    config = get_effective_llm_config()
    return {
        "status": "ok",
        "llm_configured": config.configured,
        "llm_mode": config.mode,
        "voice_configured": VoiceClient().configured,
    }
```

- [ ] **Step 6: 运行确认通过**

Run: `cd backend && .\.venv\Scripts\python.exe -m app.smoke_test`
Expected: PASS，输出 `smoke ok: ...`

- [ ] **Step 7: 提交**

```bash
git add backend/app/config.py backend/app/services/voice.py backend/app/main.py backend/app/smoke_test.py
git commit -m "feat: 新增 MiMo 语音服务 VoiceClient 与 health.voice_configured"
```

---

### Task 2: Schema 变更 + `/voice/transcribe` 端点

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routers/training.py:131`
- Create: `backend/app/routers/voice.py`
- Modify: `backend/app/main.py`
- Test: `backend/app/smoke_test.py`

- [ ] **Step 1: 先在 smoke_test.py 写失败断言**

`smoke_test.py` 顶部已有 `from app.services.voice import ...` 一行改为：

```python
from app.services.voice import VoiceClient, VoiceError, VoiceTimeoutError, is_wav_base64
```

在 `run()` 里 `assert_openai_compatible_messages_are_sendable()` 调用之后加：

```python
    response = client.post(
        "/api/voice/transcribe",
        json={"audio_base64": fake_wav_base64(), "mime_type": "audio/wav"},
    )
    assert response.status_code == 401, response.text
    response = client.post(
        "/api/voice/transcribe",
        headers=sales_headers,
        json={"audio_base64": fake_wav_base64(), "mime_type": "audio/wav"},
    )
    assert response.status_code == 503, response.text
```

注意：这段必须放在 `sales_headers = login(client, "sales")` 之后。

在 `start_session()` 助手里 `assert body["messages"][0]["role"] == "customer"` 之后加：

```python
    assert all("id" in message for message in body["messages"])
```

在文件中（`run()` 之前）新增助手函数：

```python
def fake_wav_base64() -> str:
    pcm = b"\x00\x01" * 160
    riff = b"RIFF" + (36 + len(pcm)).to_bytes(4, "little") + b"WAVE"
    return base64.b64encode(riff + pcm).decode("ascii")
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .\.venv\Scripts\python.exe -m app.smoke_test`
Expected: FAIL（404 Not Found，因为路由还没挂载）

- [ ] **Step 3: 修改 `backend/app/schemas.py`**

`MessageOut` 加 `id`：

```python
class MessageOut(BaseModel):
    id: int
    role: str
    content: str
```

在 `MessageOut` 附近（`SuggestionOut` 之前）新增两个入参 schema：

```python
class VoiceTranscribeIn(BaseModel):
    audio_base64: str
    mime_type: str = "audio/wav"


class VoiceSpeechIn(BaseModel):
    text: str
```

- [ ] **Step 4: 修改 `backend/app/routers/training.py`**

`send_message` 末尾（约 131 行）的显式构造改为：

```python
    return MessageOut(id=message.id, role=message.role, content=message.content)
```

- [ ] **Step 5: 创建 `backend/app/routers/voice.py`**

```python
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
    is_wav_base64,
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
```

说明：识别为空时返回 200 + `{"text": ""}`，由前端提示"未识别到有效语音"。

- [ ] **Step 6: 挂载路由（`backend/app/main.py`）**

import 区 `from app.routers import ...` 一行加入 `voice`：

```python
from app.routers import auth, dashboard, knowledge, settings, training, voice
```

`include_router` 区域加：

```python
app.include_router(voice.router, prefix="/api")
```

- [ ] **Step 7: 运行确认通过**

Run: `cd backend && .\.venv\Scripts\python.exe -m app.smoke_test`
Expected: PASS

- [ ] **Step 8: 提交**

```bash
git add backend/app/schemas.py backend/app/routers/training.py backend/app/routers/voice.py backend/app/main.py backend/app/smoke_test.py
git commit -m "feat: 新增语音识别端点 /voice/transcribe，MessageOut 输出消息 id"
```

---

### Task 3: `/voice/speech` 端点（截断、超时、错误映射）+ 完整语音回归

**Files:**
- Modify: `backend/app/routers/voice.py`
- Test: `backend/app/smoke_test.py`

- [ ] **Step 1: 先在 smoke_test.py 写失败断言**

在 `run()` 之前新增完整回归函数：

```python
def assert_voice_flow(client: TestClient, headers: dict):
    settings.mimo_api_key = "sk-mimo-test"

    async def fake_transcribe(self, audio_base64, mime_type):
        assert mime_type == "audio/wav"
        return "你好，我想了解一下价格。"

    async def fake_synthesize(self, text):
        captured_tts.append(text)
        return b"RIFF-fake-wav"

    captured_tts = []
    original_transcribe = VoiceClient.transcribe
    original_synthesize = VoiceClient.synthesize
    VoiceClient.transcribe = fake_transcribe
    VoiceClient.synthesize = fake_synthesize
    try:
        # 未配置检查已在 run() 覆盖；此处 Key 已配置
        health = client.get("/api/health")
        assert health.json()["voice_configured"] is True

        # 非 wav（magic number 校验）→ 400
        response = client.post(
            "/api/voice/transcribe",
            headers=headers,
            json={"audio_base64": base64.b64encode(b"not-a-wav-file").decode("ascii"), "mime_type": "audio/wav"},
        )
        assert response.status_code == 400, response.text
        # mime 不匹配 → 400
        response = client.post(
            "/api/voice/transcribe",
            headers=headers,
            json={"audio_base64": fake_wav_base64(), "mime_type": "audio/mp3"},
        )
        assert response.status_code == 400, response.text
        # 超大音频 → 413
        response = client.post(
            "/api/voice/transcribe",
            headers=headers,
            json={"audio_base64": "UklGR" + "A" * (8 * 1024 * 1024), "mime_type": "audio/wav"},
        )
        assert response.status_code == 413, response.text
        # 正常识别
        response = client.post(
            "/api/voice/transcribe",
            headers=headers,
            json={"audio_base64": fake_wav_base64(), "mime_type": "audio/wav"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["text"] == "你好，我想了解一下价格。"

        # 正常合成 → audio/wav 字节流，文本先 trim
        response = client.post("/api/voice/speech", headers=headers, json={"text": "  价格方面我们可以再谈。 "})
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("audio/wav")
        assert response.content == b"RIFF-fake-wav"
        assert captured_tts[-1] == "价格方面我们可以再谈。"
        # 超 500 字自动截断，不报错
        response = client.post("/api/voice/speech", headers=headers, json={"text": "长" * 600})
        assert response.status_code == 200, response.text
        assert len(captured_tts[-1]) == TTS_MAX_CHARS
        # 空文本 → 400
        response = client.post("/api/voice/speech", headers=headers, json={"text": "   "})
        assert response.status_code == 400, response.text
    finally:
        VoiceClient.transcribe = original_transcribe
        VoiceClient.synthesize = original_synthesize

    # 超时 → 504；其它上游错误 → 502
    async def timeout_transcribe(self, audio_base64, mime_type):
        raise VoiceTimeoutError("timeout")

    async def broken_synthesize(self, text):
        raise VoiceError("boom")

    VoiceClient.transcribe = timeout_transcribe
    VoiceClient.synthesize = broken_synthesize
    try:
        response = client.post(
            "/api/voice/transcribe",
            headers=headers,
            json={"audio_base64": fake_wav_base64(), "mime_type": "audio/wav"},
        )
        assert response.status_code == 504, response.text
        assert "超时" in response.json()["detail"]
        response = client.post("/api/voice/speech", headers=headers, json={"text": "你好"})
        assert response.status_code == 502, response.text
    finally:
        VoiceClient.transcribe = original_transcribe
        VoiceClient.synthesize = original_synthesize
        settings.mimo_api_key = ""
```

顶部 import 行补充 `TTS_MAX_CHARS`：

```python
from app.services.voice import TTS_MAX_CHARS, VoiceClient, VoiceError, VoiceTimeoutError, is_wav_base64
```

在 `run()` 的 `print("smoke ok: ...")` 之前加：

```python
    assert_voice_flow(client, sales_headers)
```

并把最后一行打印改为：

```python
    print("smoke ok: documents, chunks, retrieval, report, voice")
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .\.venv\Scripts\python.exe -m app.smoke_test`
Expected: FAIL（`/api/voice/speech` 返回 404）

- [ ] **Step 3: 在 `backend/app/routers/voice.py` 追加 speech 端点**

```python
@router.post("/speech")
async def synthesize(payload: VoiceSpeechIn, _: User = Depends(current_user)):
    client = VoiceClient()
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
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && .\.venv\Scripts\python.exe -m app.smoke_test`
Expected: PASS，输出 `smoke ok: documents, chunks, retrieval, report, voice`

- [ ] **Step 5: 提交**

```bash
git add backend/app/routers/voice.py backend/app/smoke_test.py
git commit -m "feat: 新增语音合成端点 /voice/speech，支持超长截断与超时/错误分层"
```

---

### Task 4: `.env.example` + 前端 `apiAudio` + `audio.js` 引擎

**Files:**
- Modify: `.env.example`
- Modify: `frontend/src/api.js`
- Create: `frontend/src/audio.js`

- [ ] **Step 1: 更新 `.env.example`**

文件末尾追加：

```env

# 小米 MiMo 语音服务（ASR/TTS）。留空则语音功能自动隐藏，纯文字训练不受影响。
SALES_COACH_MIMO_API_KEY=
SALES_COACH_MIMO_BASE_URL=https://api.xiaomimimo.com
SALES_COACH_MIMO_ASR_MODEL=mimo-v2.5-asr
SALES_COACH_MIMO_TTS_MODEL=mimo-v2.5-tts
```

- [ ] **Step 2: `frontend/src/api.js` 追加 `apiAudio`**

```javascript
export async function apiAudio(path, body) {
  const token = localStorage.getItem("salesCoachToken");
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    let detail = "请求失败";
    try {
      const parsed = await response.json();
      detail = parsed.detail || detail;
    } catch {
      const text = await response.text().catch(() => "");
      if (text) detail = text;
    }
    throw new Error(detail);
  }
  return response.blob();
}
```

- [ ] **Step 3: 创建 `frontend/src/audio.js`（完整内容）**

```javascript
// 语音引擎：录音（含 WAV 编码）与播放。零 React 依赖，
// 组件只通过回调和返回值消费，不接触 MediaRecorder/Audio 细节。

const TARGET_SAMPLE_RATE = 16000;
const MAX_RECORD_SECONDS = 60;
const WARNING_SECONDS = 55;

export const RECORDER_STATES = {
  idle: "idle",
  recording: "recording",
  warning: "warning",
  processing: "processing",
};

export class AudioRecorder {
  constructor(onStateChange, onAutoStop) {
    this.onStateChange = onStateChange || (() => {});
    this.onAutoStop = onAutoStop || null;
    this.state = RECORDER_STATES.idle;
    this.mediaRecorder = null;
    this.stream = null;
    this.chunks = [];
    this.timer = null;
    this.elapsed = 0;
    this.settling = null;
  }

  static supported() {
    return Boolean(
      typeof navigator !== "undefined" &&
        navigator.mediaDevices &&
        navigator.mediaDevices.getUserMedia &&
        typeof window.MediaRecorder !== "undefined"
    );
  }

  _setState(state) {
    this.state = state;
    this.onStateChange(state);
  }

  async start() {
    if (this.state === RECORDER_STATES.recording || this.state === RECORDER_STATES.warning) return;
    if (!AudioRecorder.supported()) {
      throw new Error("当前浏览器不支持录音，请使用 Chrome 或 Edge");
    }
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this.chunks = [];
    this.elapsed = 0;
    this.settling = null;
    this.mediaRecorder = new MediaRecorder(this.stream);
    this.mediaRecorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) this.chunks.push(event.data);
    };
    this.mediaRecorder.start();
    this._setState(RECORDER_STATES.recording);
    this.timer = window.setInterval(async () => {
      this.elapsed += 1;
      if (this.elapsed >= MAX_RECORD_SECONDS) {
        let blob = null;
        try {
          blob = await this._settle();
        } catch {
          blob = null;
        }
        if (blob && this.onAutoStop) this.onAutoStop(blob);
      } else if (this.elapsed >= WARNING_SECONDS && this.state === RECORDER_STATES.recording) {
        this._setState(RECORDER_STATES.warning);
      }
    }, 1000);
  }

  stop() {
    return this._settle();
  }

  _settle() {
    if (this.settling) return this.settling;
    if (!this.mediaRecorder || this.mediaRecorder.state === "inactive") {
      return Promise.resolve(null);
    }
    window.clearInterval(this.timer);
    this.timer = null;
    this.settling = new Promise((resolve, reject) => {
      this.mediaRecorder.onstop = async () => {
        this._setState(RECORDER_STATES.processing);
        try {
          const blob = new Blob(this.chunks, { type: this.mediaRecorder.mimeType || "audio/webm" });
          const wavBlob = await encodeWav(blob);
          this._cleanup();
          this._setState(RECORDER_STATES.idle);
          resolve(wavBlob);
        } catch (err) {
          this._cleanup();
          this._setState(RECORDER_STATES.idle);
          reject(err);
        } finally {
          this.settling = null;
        }
      };
      this.mediaRecorder.stop();
    });
    return this.settling;
  }

  cancel() {
    window.clearInterval(this.timer);
    this.timer = null;
    if (this.mediaRecorder && this.mediaRecorder.state !== "inactive") {
      this.mediaRecorder.onstop = null;
      this.mediaRecorder.stop();
    }
    this.settling = null;
    this._cleanup();
    this._setState(RECORDER_STATES.idle);
  }

  _cleanup() {
    if (this.stream) {
      this.stream.getTracks().forEach((track) => track.stop());
      this.stream = null;
    }
    this.mediaRecorder = null;
    this.chunks = [];
  }
}

// 解码 → 单声道 → 重采样 16kHz → Int16 量化 → WAV
async function encodeWav(blob) {
  const arrayBuffer = await blob.arrayBuffer();
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  const decodeContext = new AudioContextClass();
  let audioBuffer;
  try {
    audioBuffer = await decodeContext.decodeAudioData(arrayBuffer);
  } finally {
    decodeContext.close();
  }
  const offline = new OfflineAudioContext(
    1,
    Math.max(1, Math.ceil(audioBuffer.duration * TARGET_SAMPLE_RATE)),
    TARGET_SAMPLE_RATE
  );
  const source = offline.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(offline.destination);
  source.start(0);
  const rendered = await offline.startRendering();
  const samples = rendered.getChannelData(0);
  return new Blob([buildWavBytes(samples)], { type: "audio/wav" });
}

function buildWavBytes(samples) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  writeString(view, 0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(view, 8, "WAVE");
  writeString(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, TARGET_SAMPLE_RATE, true);
  view.setUint32(28, TARGET_SAMPLE_RATE * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(view, 36, "data");
  view.setUint32(40, samples.length * 2, true);
  let offset = 44;
  for (let i = 0; i < samples.length; i += 1, offset += 2) {
    // Float32(-1..1) 必须量化为 Int16，否则 16-bit WAV 头配 Float 数据会全是爆音
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
  }
  return buffer;
}

function writeString(view, offset, text) {
  for (let i = 0; i < text.length; i += 1) {
    view.setUint8(offset + i, text.charCodeAt(i));
  }
}

export class AudioPlayer {
  constructor() {
    this.audio = null;
  }

  playBlob(blob, onSettled) {
    this.stop();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    this.audio = audio;
    const settle = () => {
      URL.revokeObjectURL(url);
      if (this.audio === audio) this.audio = null;
      if (onSettled) onSettled();
    };
    audio.onended = settle;
    audio.onerror = settle;
    audio.play().catch(settle);
  }

  stop() {
    if (!this.audio) return;
    const audio = this.audio;
    this.audio = null;
    audio.onended = null;
    audio.onerror = null;
    audio.pause();
    if (audio.src && audio.src.startsWith("blob:")) URL.revokeObjectURL(audio.src);
  }

  dispose() {
    this.stop();
  }
}

export function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] || "");
    reader.onerror = () => reject(new Error("音频读取失败，请重试"));
    reader.readAsDataURL(blob);
  });
}
```

- [ ] **Step 4: 构建验证**

Run: `cd frontend && npm run build`
Expected: PASS（audio.js 尚未被引用，构建通过即可；Vite 不会因未引用文件报错）

- [ ] **Step 5: 提交**

```bash
git add .env.example frontend/src/api.js frontend/src/audio.js
git commit -m "feat: 新增语音引擎模块 audio.js 与 apiAudio 请求封装"
```

---

### Task 5: `voice.jsx` UI 组件

**Files:**
- Create: `frontend/src/voice.jsx`

- [ ] **Step 1: 创建 `frontend/src/voice.jsx`（完整内容）**

```jsx
import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { AudioRecorder, RECORDER_STATES, blobToBase64 } from "./audio";

export function MicButton({ disabled, onResult, onError, onRecordingChange }) {
  const recorderRef = useRef(null);
  const deliverRef = useRef(() => {});
  const callbacksRef = useRef({ onResult, onError, onRecordingChange });
  callbacksRef.current = { onResult, onError, onRecordingChange };
  const [state, setState] = useState(RECORDER_STATES.idle);
  const [isTranscribing, setIsTranscribing] = useState(false);

  async function deliver(wavBlob) {
    setIsTranscribing(true);
    try {
      const audioBase64 = await blobToBase64(wavBlob);
      const result = await api("/voice/transcribe", {
        method: "POST",
        body: JSON.stringify({ audio_base64: audioBase64, mime_type: "audio/wav" }),
      });
      const recognized = (result.text || "").trim();
      if (!recognized) throw new Error("未识别到有效语音，请重试");
      callbacksRef.current.onResult(recognized);
    } catch (err) {
      callbacksRef.current.onError(err.message || "语音识别失败，请重试");
    } finally {
      setIsTranscribing(false);
    }
  }
  deliverRef.current = deliver;

  useEffect(() => {
    const recorder = new AudioRecorder(
      (next) => {
        setState(next);
        const recording = next === RECORDER_STATES.recording || next === RECORDER_STATES.warning;
        callbacksRef.current.onRecordingChange?.(recording);
      },
      (blob) => {
        void deliverRef.current(blob);
      }
    );
    recorderRef.current = recorder;
    return () => {
      recorder.cancel();
      callbacksRef.current.onRecordingChange?.(false);
    };
  }, []);

  const recording = state === RECORDER_STATES.recording || state === RECORDER_STATES.warning;

  async function handleClick() {
    const recorder = recorderRef.current;
    if (!recorder || isTranscribing) return;
    if (recording) {
      try {
        const wavBlob = await recorder.stop();
        if (wavBlob) await deliver(wavBlob);
      } catch (err) {
        onError(err.message || "录音失败，请重试");
      }
      return;
    }
    try {
      await recorder.start();
    } catch (err) {
      onError(err.message || "无法启动录音");
    }
  }

  const label = isTranscribing
    ? "识别中…"
    : recording
      ? state === RECORDER_STATES.warning
        ? "即将到限，点击结束"
        : "点击结束"
      : "语音输入";

  return (
    <button
      type="button"
      className={`mic-button ${recording ? "is-recording" : ""} ${state === RECORDER_STATES.warning ? "is-warning" : ""}`}
      disabled={disabled || isTranscribing}
      onClick={handleClick}
      title={recording ? "再次点击结束并发送" : "点击开始语音输入"}
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 4a3 3 0 0 1 3 3v5a3 3 0 0 1-6 0V7a3 3 0 0 1 3-3z"></path>
        <path d="M6 11a6 6 0 0 0 12 0"></path>
        <path d="M12 17v3"></path>
      </svg>
      <span>{label}</span>
    </button>
  );
}

export function PlayButton({ status, onClick }) {
  const title =
    status === "loading"
      ? "正在合成语音"
      : status === "playing"
        ? "停止播放"
        : status === "error"
          ? "语音合成失败，点击重试"
          : "播放这条回复";
  return (
    <button
      type="button"
      className={`play-button ${status === "playing" ? "is-playing" : ""} ${status === "error" ? "is-error" : ""}`}
      onClick={onClick}
      title={title}
      aria-label={title}
    >
      {status === "loading" ? (
        <span className="play-loading" aria-hidden="true" />
      ) : (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          {status === "playing" ? <path d="M8 5v14M16 5v14"></path> : <path d="M8 5l11 7-11 7z"></path>}
        </svg>
      )}
      {status === "error" && (
        <i className="play-error-dot" aria-hidden="true">
          !
        </i>
      )}
    </button>
  );
}

export function AutoReadToggle({ enabled, onChange }) {
  return (
    <label className="auto-read-toggle" title="客户回复后自动朗读">
      <input type="checkbox" checked={enabled} onChange={(event) => onChange(event.target.checked)} />
      <span>自动朗读</span>
    </label>
  );
}
```

- [ ] **Step 2: 构建验证**

Run: `cd frontend && npm run build`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add frontend/src/voice.jsx
git commit -m "feat: 新增语音 UI 组件 MicButton/PlayButton/AutoReadToggle"
```

---

### Task 6: `App.jsx` 接线 + 样式

**Files:**
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: 修改 imports（`frontend/src/App.jsx` 第 3 行附近）**

```jsx
import { api, apiAudio, apiForm } from "./api";
import { AudioPlayer } from "./audio";
import { AutoReadToggle, MicButton, PlayButton } from "./voice";
```

（原 `import { api, apiForm } from "./api";` 替换为上面三行，`import "./styles.css";` 保持最后）

- [ ] **Step 2: App 渲染处给 Chat 传 `voiceEnabled`**

替换：

```jsx
          {view === "chat" && <Chat session={session} onError={setError} onSession={setSession} onReset={resetCurrentChat} onReport={(nextReport) => { setReport(withSessionMeta(nextReport, session)); setView("report"); loadAll(); }} />}
```

为：

```jsx
          {view === "chat" && <Chat session={session} voiceEnabled={runtimeStatus?.voice_configured === true} onError={setError} onSession={setSession} onReset={resetCurrentChat} onReport={(nextReport) => { setReport(withSessionMeta(nextReport, session)); setView("report"); loadAll(); }} />}
```

- [ ] **Step 3: Chat 组件签名与状态**

替换：

```jsx
function Chat({ session, onSession, onReport, onError, onReset }) {
  const [text, setText] = useState("");
  const [showExample, setShowExample] = useState(false);
  const [suggestion, setSuggestion] = useState(null);
  const [isSuggesting, setIsSuggesting] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [isFinishing, setIsFinishing] = useState(false);
  const inputRef = useRef(null);
  const suggestionRef = useRef(null);
```

为：

```jsx
function Chat({ session, onSession, onReport, onError, onReset, voiceEnabled }) {
  const [text, setText] = useState("");
  const [showExample, setShowExample] = useState(false);
  const [suggestion, setSuggestion] = useState(null);
  const [isSuggesting, setIsSuggesting] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [isFinishing, setIsFinishing] = useState(false);
  const [isVoiceRecording, setIsVoiceRecording] = useState(false);
  const [autoRead, setAutoRead] = useState(() => localStorage.getItem("salesCoachAutoRead") !== "off");
  const [playback, setPlayback] = useState({ key: "", status: "idle" });
  const playerRef = useRef(null);
  const audioCache = useRef(new Map());
  const inputRef = useRef(null);
  const suggestionRef = useRef(null);
```

- [ ] **Step 4: Chat 内新增播放器生命周期、缓存与朗读函数**

在 Chat 组件里 `const exampleReply = ...` 一行之后、`useEffect(() => { if (!showExample) ...` 之前插入：

```jsx
  useEffect(() => {
    playerRef.current = new AudioPlayer();
    audioCache.current = new Map();
    setPlayback({ key: "", status: "idle" });
    return () => {
      playerRef.current?.dispose();
    };
  }, [session?.id]);

  function toggleAutoRead(next) {
    setAutoRead(next);
    localStorage.setItem("salesCoachAutoRead", next ? "on" : "off");
  }

  function messageCacheKey(message, index) {
    return `${session.id}:${message.id ?? index}`;
  }

  async function speakMessage(message, index) {
    if (!playerRef.current) return;
    const key = messageCacheKey(message, index);
    if (playback.key === key && playback.status === "playing") {
      playerRef.current.stop();
      setPlayback({ key: "", status: "idle" });
      return;
    }
    try {
      let blob = audioCache.current.get(key);
      if (!blob) {
        setPlayback({ key, status: "loading" });
        blob = await apiAudio("/voice/speech", { text: (message.content || "").trim() });
        audioCache.current.set(key, blob);
      }
      setPlayback({ key, status: "playing" });
      playerRef.current.playBlob(blob, () => {
        setPlayback((current) => (current.key === key ? { key: "", status: "idle" } : current));
      });
    } catch {
      setPlayback({ key, status: "error" });
    }
  }
```

- [ ] **Step 5: 重构 `send()`，支持外部文本 + 自动朗读**

替换整个 `send()` 函数：

```jsx
  async function send(forcedContent) {
    const content = (forcedContent ?? text).trim();
    if (!content || isSending || isFinishing) return;
    setText("");
    setSuggestion(null);
    setShowExample(false);
    setIsSending(true);
    playerRef.current?.stop();
    setPlayback({ key: "", status: "idle" });
    onSession({ ...session, messages: [...session.messages, { role: "sales", content }] });
    try {
      await api(`/training/sessions/${session.id}/messages`, { method: "POST", body: JSON.stringify({ content }) });
      const updated = await api(`/training/sessions/${session.id}`);
      onSession(updated);
      if (voiceEnabled && autoRead) {
        const lastIndex = updated.messages.map((message) => message.role).lastIndexOf("customer");
        if (lastIndex >= 0) speakMessage(updated.messages[lastIndex], lastIndex);
      }
    } catch (err) {
      onError(err.message);
    } finally {
      setIsSending(false);
    }
  }
```

注意：`speakMessage` 内部 `playback` 闭包是旧值无碍——自动朗读时必然不在播放态。

- [ ] **Step 6: 消息气泡加播放按钮**

替换：

```jsx
          {session.messages.map((msg, index) => (
            <div key={index} className={`msg ${msg.role === "sales" ? "sales" : ""}`}><span className="who">{msg.role === "sales" ? "业务员" : "客户"}</span><div className="bubble">{msg.content}</div></div>
          ))}
```

为：

```jsx
          {session.messages.map((msg, index) => (
            <div key={msg.id ?? index} className={`msg ${msg.role === "sales" ? "sales" : ""}`}>
              <span className="who">{msg.role === "sales" ? "业务员" : "客户"}</span>
              <div className="bubble-row">
                <div className="bubble">{msg.content}</div>
                {voiceEnabled && msg.role === "customer" && (
                  <PlayButton
                    status={playback.key === messageCacheKey(msg, index) ? playback.status : "idle"}
                    onClick={() => speakMessage(msg, index)}
                  />
                )}
              </div>
            </div>
          ))}
```

- [ ] **Step 7: composer-tools 加自动朗读开关**

替换（composer-tools 内部开头）：

```jsx
          <div className="composer-tools">
            <span>{isSending ? "客户正在思考你的回应..." : salesTurns >= 3 ? "已满足验收轮次，可以进入复盘。" : "建议至少完成 3 轮回应。"}</span>
```

为：

```jsx
          <div className="composer-tools">
            <span>{isSending ? "客户正在思考你的回应..." : salesTurns >= 3 ? "已满足验收轮次，可以进入复盘。" : "建议至少完成 3 轮回应。"}</span>
            {voiceEnabled && <AutoReadToggle enabled={autoRead} onChange={toggleAutoRead} />}
```

- [ ] **Step 8: composer-row 加麦克风按钮**

替换：

```jsx
          <div className="composer-row">
            <input ref={inputRef} value={text} disabled={isSending || isFinishing} onChange={(e) => setText(e.target.value)} placeholder={isSending ? "等待客户回复中" : "输入你的回应"} onKeyDown={(e) => { if (e.key === "Enter") send(); }} />
            <button className="send-button" disabled={!text.trim() || isSending || isFinishing} onClick={send}>{isSending ? "发送中" : "发送"}</button>
          </div>
```

为：

```jsx
          <div className={`composer-row ${voiceEnabled ? "has-voice" : ""}`}>
            {voiceEnabled && (
              <MicButton
                disabled={isSending || isFinishing}
                onError={onError}
                onRecordingChange={setIsVoiceRecording}
                onResult={(recognized) => send(recognized)}
              />
            )}
            <input ref={inputRef} value={text} disabled={isSending || isFinishing} onChange={(e) => setText(e.target.value)} placeholder={isSending ? "等待客户回复中" : isVoiceRecording ? "正在录音，再次点击麦克风结束" : "输入你的回应"} onKeyDown={(e) => { if (e.key === "Enter") send(); }} />
            <button className="send-button" disabled={!text.trim() || isSending || isFinishing} onClick={() => send()}>{isSending ? "发送中" : "发送"}</button>
          </div>
```

- [ ] **Step 9: `frontend/src/styles.css` 末尾追加语音样式**

```css
/* ===== 语音输入 / 输出 ===== */
.composer-row.has-voice {
  grid-template-columns: auto minmax(0, 1fr) auto;
}

.mic-button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 48px;
  padding: 0 16px;
  border: 1px solid rgba(222, 229, 239, 0.88);
  border-radius: 999px;
  background: #f6f8fc;
  color: #3c4657;
  font-size: 13px;
  white-space: nowrap;
  transition: background 180ms var(--ease), border-color 180ms var(--ease), color 180ms var(--ease);
}

.mic-button svg {
  width: 18px;
  height: 18px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.mic-button:hover { background: #eef3fa; border-color: #c9d7ec; }
.mic-button:disabled { cursor: not-allowed; opacity: 0.55; }

.mic-button.is-recording {
  border-color: rgba(217, 83, 79, 0.55);
  background: #fdecea;
  color: #c5221f;
  animation: micPulse 1.6s ease-in-out infinite;
}

.mic-button.is-warning {
  border-color: rgba(217, 160, 51, 0.65);
  background: #fdf3e0;
  color: #b26a00;
}

@keyframes micPulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(217, 83, 79, 0.28); }
  50% { box-shadow: 0 0 0 7px rgba(217, 83, 79, 0); }
}

.bubble-row {
  display: flex;
  align-items: flex-end;
  gap: 8px;
}

.msg.sales .bubble-row { justify-content: flex-end; }

.play-button {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  flex: none;
  border: 1px solid rgba(222, 229, 239, 0.88);
  border-radius: 999px;
  background: #fff;
  color: #5f6b7c;
  transition: color 180ms var(--ease), border-color 180ms var(--ease), background 180ms var(--ease);
}

.play-button svg {
  width: 14px;
  height: 14px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.play-button:hover { color: #0b57d0; border-color: #c9d7ec; }
.play-button.is-playing { color: #0b57d0; border-color: #bfd3f4; background: #eef3fd; }
.play-button.is-error { color: #9aa4b2; }

.play-loading {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(11, 87, 208, 0.25);
  border-top-color: #0b57d0;
  border-radius: 999px;
  animation: spinSoft 0.8s linear infinite;
}

.play-error-dot {
  position: absolute;
  top: -4px;
  right: -4px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 12px;
  height: 12px;
  border-radius: 999px;
  background: #d93025;
  color: #fff;
  font-size: 9px;
  font-style: normal;
  line-height: 1;
}

.auto-read-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #5f6b7c;
  font-size: 12px;
  cursor: pointer;
  user-select: none;
}

.auto-read-toggle input { accent-color: #0b57d0; }
```

- [ ] **Step 10: 响应式补丁**

`styles.css` 约 6488 行的媒体查询里，找到：

```css
  .composer-row { grid-template-columns: 1fr; }
```

在其后一行加：

```css
  .composer-row.has-voice { grid-template-columns: auto minmax(0, 1fr) auto; }
```

- [ ] **Step 11: 构建验证**

Run: `cd frontend && npm run build`
Expected: PASS

- [ ] **Step 12: 提交**

```bash
git add frontend/src/App.jsx frontend/src/styles.css
git commit -m "feat: 训练对话接入语音输入与自动朗读，未配置时自动隐藏"
```

---

### Task 7: 全量验证 + 手工 E2E

**Files:** 无代码改动（验证任务）

- [ ] **Step 1: 后端 smoke 全量回归**

Run: `cd backend && .\.venv\Scripts\python.exe -m app.smoke_test`
Expected: 输出 `smoke ok: documents, chunks, retrieval, report, voice`

- [ ] **Step 2: 前端构建**

Run: `cd frontend && npm run build`
Expected: PASS

- [ ] **Step 3: 无 Key 降级验证（不配置 SALES_COACH_MIMO_API_KEY）**

1. 启动 `.\start-mvp.ps1`（或分别启动前后端），登录 `sales/123456`。
2. 进入训练对话，确认：**没有麦克风按钮、没有播放按钮、没有自动朗读开关**。
3. 完整走一轮文字对话 + 复盘，确认功能不受影响。

- [ ] **Step 4: 真 Key E2E（在 `backend/.env` 配置 `SALES_COACH_MIMO_API_KEY=<真实Key>` 后重启后端）**

1. 开始一次训练，确认客户第一条回复气泡旁出现播放按钮。
2. 点击播放按钮 → 听到客户语音；再点一次 → 停止；悬停失败态可看 tooltip。
3. 打开"自动朗读"，发送一条文字 → 客户新回复自动朗读。
4. 点击麦克风 → 说中文（如"价格方面能不能再优惠一点"）→ 点击结束 → 识别文本自动发送，客户回复并朗读。
5. 录音到 55s 附近观察黄色预警（可用短录音替代验证按钮状态流转），60s 自动停止发送。
6. 关闭"自动朗读"开关 → 新回复不再朗读；刷新页面后开关状态保持。
7. 切换会话 / 回到历史再进入 → 无残留播放，重听按钮按需重新合成。
8. 临时把 `.env` 的 Key 改错重启 → 发送语音：识别失败有中文提示且不阻塞打字；播放按钮显示错误角标。

- [ ] **Step 5: 最终提交（如有验证中的微调）**

```bash
git status
# 无改动则跳过；有改动则：
git add -A && git commit -m "fix: 语音功能验证修复"
```

---

## Self-Review 结论

- **Spec 覆盖：** 设计文档 8 节全部有对应任务——配置（T1）、VoiceClient（T1）、transcribe+校验（T2）、speech+截断+错误分层（T3）、MessageOut.id（T2）、health（T1）、apiAudio（T4）、audio.js 引擎（T4）、voice.jsx（T5）、Chat 接线与交互细节（T6）、降级矩阵（T6 的条件渲染 + T7 步骤 3）、验证（T7）。`.env.example`（T4）。无遗漏。
- **类型一致性：** `VoiceError`/`VoiceTimeoutError`/`is_wav_base64`/`TTS_MAX_CHARS`/`MAX_AUDIO_BASE64_LENGTH` 在 voice.py 定义与 router/smoke 引用一致；前端 `RECORDER_STATES`、`AudioPlayer.playBlob(blob, onSettled)`、`apiAudio` 签名跨任务一致。
- **已知注意点：** 55s/60s 时限逻辑在 `AudioRecorder` 内部计时器实现；`_settle()` 有 `settling` 防重入，自动停止与手动点击竞态安全。
