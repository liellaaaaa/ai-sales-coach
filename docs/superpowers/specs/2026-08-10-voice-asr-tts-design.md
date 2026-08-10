# 语音识别与语音输出（ASR / TTS）设计

> 目标：在"客户情景陪练"对话中加入语音输入与语音输出，让业务员可以用嘴跟 AI 客户交流，而不是纯打字。语音是增强项，文字链路保持不变，任何语音故障都不能阻塞训练。

**服务商：** 小米 MiMo（OpenAI 兼容接口）。用户已持有 API Key，办公机可访问公网。

**架构原则：** 后端代理。API Key 只留在服务端 `.env`，前端永远不接触密钥，与现有 LLM Key 的管理模式一致。

---

## 一、需求与已确认的产品决策

| 决策点 | 结论 |
|---|---|
| 网络环境 | 办公机可访问公网，允许调用云端语音 API |
| 服务商 | 小米 MiMo（`mimo-v2.5-asr` / `mimo-v2.5-tts`），用户已有 Key |
| Key 配置 | 只走 `.env`（`SALES_COACH_MIMO_API_KEY`），本期不做管理员后台 UI 配置 |
| 语音输入交互 | 点击麦克风开始 → 再次点击结束 → 识别后**自动发送** |
| 语音输出交互 | 客户回复**自动朗读**（有开关，默认开）+ 每条客户气泡可**重听** |
| 音色 | 只用默认音色 `mimo_default`；音色定制 / 音色设计明确不做 |
| 降级 | 未配 Key 时语音 UI 完全不渲染，纯文字体验不变 |
| 音色合成 / 长文分段朗读 | 不做（见"非目标"） |

**非目标（本期明确不做）：**
- 音色定制 / 音色设计（MiMo 的 voice design 能力）。
- 后端管理员后台的语音 Key 配置 UI。
- 长文本自动分段合成再拼接音频（客户回复被 prompt 限制在 80 字内，500 字截断已足够兜底）。
- 把 ~3000 行 `App.jsx` 全量拆成组件树——那是独立的下一个任务，本期只保证新增语音代码模块化。
- 流式（streaming）识别 / 合成。
- 语音消息在服务端的持久化缓存。

---

## 二、小米 MiMo API 对接要点

两个能力都是 **OpenAI 兼容** 的 `POST /v1/chat/completions`，同一 base URL、同一 Key：

- **Base URL：** `https://api.xiaomimimo.com`
- **鉴权：** 请求头 `Authorization: Bearer $MIMO_API_KEY`（也支持 `api-key:` 头，统一用 Bearer）

### ASR（`mimo-v2.5-asr`）

请求体：

```json
{
  "model": "mimo-v2.5-asr",
  "messages": [
    {
      "role": "user",
      "content": [
        { "type": "input_audio",
          "input_audio": { "data": "data:audio/wav;base64,<BASE64_AUDIO>" } }
      ]
    }
  ],
  "asr_options": { "language": "auto" }
}
```

响应：识别文本在 `choices[0].message.content`。

### TTS（`mimo-v2.5-tts`）

请求体（`messages` 里 user 放语气描述、assistant 放待合成文本）：

```json
{
  "model": "mimo-v2.5-tts",
  "messages": [
    { "role": "user", "content": "<固定的中性语气描述>" },
    { "role": "assistant", "content": "<待合成文本>" }
  ],
  "audio": { "format": "wav", "voice": "mimo_default" }
}
```

响应：音频 base64 在 `choices[0].message.audio.data`，格式为 wav。后端 base64 解码后直接以 `audio/wav` 字节流返回给前端。

> 注：TTS 的 `user.content` 是音色/风格描述位。本期用**一句固定的中性描述**占位（如"用自然、平稳、接近真人客服的语气朗读"），不暴露给用户配置。

---

## 三、后端设计

### 3.1 配置（`config.py` + `.env.example`）

沿用 `SALES_COACH_` 前缀，新增 4 项，只有 Key 必填，其余有默认值：

```env
SALES_COACH_MIMO_API_KEY=
SALES_COACH_MIMO_BASE_URL=https://api.xiaomimimo.com
SALES_COACH_MIMO_ASR_MODEL=mimo-v2.5-asr
SALES_COACH_MIMO_TTS_MODEL=mimo-v2.5-tts
```

`.env.example` 只放占位值（遵守 GitHub 入库边界）。

### 3.2 新服务 `services/voice.py`（`VoiceClient`，风格对齐 `LLMClient`）

- `configured` —— 是否配置了 `mimo_api_key`。
- `transcribe(audio_base64: str, mime_type: str) -> str`
  - 拼 `input_audio` 消息体 + `asr_options.language="auto"`，POST `chat/completions`。
  - 取 `choices[0].message.content`。
- `synthesize(text: str) -> bytes`
  - messages：user=固定语气描述，assistant=trim 后的文本。
  - `audio: {format:"wav", voice:"mimo_default"}`。
  - 取 `choices[0].message.audio.data`，base64 解码成 wav 字节返回。
- httpx 超时 **30s**（connect 独立更短）。失败抛异常，由路由层区分超时/其它错误。

### 3.3 新路由 `routers/voice.py`（全部走现有 JWT 鉴权）

| 端点 | 入参 | 出参 | 说明 |
|---|---|---|---|
| `POST /api/voice/transcribe` | `{audio_base64, mime_type}` | `{text}` | 音频转文本 |
| `POST /api/voice/speech` | `{text}` | `audio/wav` 字节流 | 文本转音频 |

鉴权说明：沿用 `current_user`（JWT Bearer Header，本地 HS256 解码 + 一次主键查询），与对话主链路 `/messages` 完全一致，不额外引入 Session/Cookie 或独立网关。

**统一的健壮性规则（两接口都适用）：**

1. **未配置 Key** → 返回 **503**，`detail` 明确说"语音功能未启用"。
2. **超时** → 捕获 `httpx.TimeoutException`，返回 **504**，`detail="语音服务响应超时，请稍后重试"`（前端据此提示，不用通用"系统错误"）。
3. **其它上游错误** → 返回 **502**。
4. 所有异常分支都带可读的中文 `detail`，前端直接展示。

**`/voice/transcribe` 专属：**

- **音频格式校验（magic number）**：base64 解码前几个字节，`audio/wav` 必须命中 `RIFF` 文件头；本期前端只发 wav，其它 mime 一律 **400** 拒绝。避免脏数据打到 MiMo 变成 502。
- **体积上限**：base64 超过约 8MB（≈4 分钟 16k 单声道 wav）返回 **413** 拒绝，防滥用。

**`/voice/speech` 专属：**

- **超长文本自动截断，不报错**：超过 **500 字**截断为前 500 字，并打一条 `warning` 日志。理由：宁可少读几个字，也不让语音功能因长文中断。
- 合成前对文本 `trim`。

### 3.4 Schema 变更（`schemas.py`）

- `MessageOut` 新增 `id: int`（训练消息表主键，必有值；`from_attributes` 直接映射）。这是给前端播放缓存做稳定 key 用的。
- 新增语音请求入参 schema：
  - `VoiceTranscribeIn`：`audio_base64: str`、`mime_type: str = "audio/wav"`。
  - `VoiceSpeechIn`：`text: str`。

### 3.5 挂载与健康检查（`main.py`）

- `include_router(voice.router, prefix="/api")`。
- `/api/health` 增加 `voice_configured` 字段（`VoiceClient().configured`）。前端 App 启动已拉 `/api/health` 存为 `runtimeStatus` 并定时刷新，直接复用这个通道。

---

## 四、前端设计

### 4.1 模块边界（重点：不往 `App.jsx` 里堆）

新增两个模块，`App.jsx` 只做接线，现有 3000 行一行不动：

```
frontend/src/
├── audio.js        # 纯逻辑引擎，零 React 依赖
│   ├── AudioRecorder   # 录音 + WAV 编码
│   └── AudioPlayer     # 播放管理
└── voice.jsx       # 语音 UI 组件
    ├── MicButton       # 麦克风按钮（开始/录音中/识别中）
    ├── PlayButton      # 客户气泡播放按钮（四态）
    └── AutoReadToggle  # 自动朗读开关
```

**`audio.js`（引擎层，不含任何 React）：**

```js
export class AudioRecorder {
  constructor(onStateChange) {}  // 回调通知 UI：idle/recording/warning/transcribing/error
  async start() {}               // 特性检测 + getUserMedia + MediaRecorder
  async stop() {}                // 返回 wav Blob 给调用方去发送
  cancel() {}
}
```

- `start()` 先做特性检测：`!navigator.mediaDevices?.getUserMedia` → 通过回调报"当前浏览器不支持录音，请使用 Chrome 或 Edge"，不进入录音。
- MediaRecorder 的 `ondataavailable` / `onstop` 等事件**全部封死在类内部**，不外泄到组件。
- **60s 上限**：到 55s 通过回调进入 `warning` 状态（UI 脉冲变黄提示"即将达到上限"），到 60s 自动 stop。
- WAV 编码内置：`AudioContext.decodeAudioData` 解码 → 重采样到 16kHz 单声道 → **Float32 量化为 Int16**（钳位到 [-1,1] 后 `v<0 ? v*0x8000 : v*0x7FFF`），WAV 头 `BitsPerSample=16`。直接写 Float 会爆音，务必量化。

```js
export class AudioPlayer {
  constructor(onStateChange) {}  // 回调：idle/loading/playing/error
  async play(url) {}             // 单实例互斥，新播放停掉旧的
  stop() {}
  dispose() {}                   // 停止并 revokeObjectURL，防内存泄漏
}
```

**`voice.jsx`（UI 层）：** 只消费上面两个引擎的回调渲染状态，不写录音/播放细节。

### 4.2 语音输入流程（ASR）

入口：`Chat` 组件输入框左侧麦克风按钮，**仅当 `runtimeStatus.voice_configured === true` 时渲染**。

1. 点击麦克风 → `AudioRecorder.start()`，按钮进入"录音中"（红色脉冲，输入框 placeholder 变"正在录音，再次点击结束"）。
2. 再次点击 → `stop()` 得到 wav Blob → 转 base64 → `POST /api/voice/transcribe`（期间按钮"识别中…"）。
3. 识别成功且非空 → 走与手动发送**完全相同**的 `send()` 路径自动发出（把 `send()` 重构成可接收外部文本参数）。
4. 失败处理（全程不影响打字）：
   - 权限被拒 → "未获得麦克风权限，请检查浏览器设置"。
   - 识别为空 → "未识别到有效语音，请重试"。
   - 504 / 502 → 直接展示后端返回的 `detail`。

**边界：** 录音中 / 识别中 / 等待客户回复（`isSending`）时麦克风按钮禁用。

### 4.3 语音输出流程（TTS）

**自动朗读：**
- 默认开启；聊天操作区放"自动朗读"开关，状态存 `localStorage`。
- `send()` 完成、拿到新的客户回复后，若开关开启 → 对最新一条客户消息调 `/api/voice/speech` 并播放。
- 合成失败**不阻塞对话**：文本气泡照常显示，错误落在播放按钮上（见下），不用全局 toast。

**手动重听：**
- 每条客户气泡加播放按钮（业务员消息不加）。
- 播放按钮**四态**：正常 ▶ / 合成中 loading / 播放中 / 失败（灰色 + 红色感叹号角标，hover tooltip"语音合成失败，请重试"）。错误就地反馈在按钮上，不遮挡内容。

**播放缓存：**
- 前端内存 Map，key = `${session.id}:${msg.id ?? index}`（`MessageOut.id` 为主，缺失退回下标兜底）。
- 命中缓存直接播，不重复合成；换会话 / 组件卸载时 `dispose()` 停止并 revoke 所有 Object URL。

**`api.js` 新增 `apiAudio()`：** 带 token、`Content-Type: application/json`，成功返回 `Blob`；失败优先解析 `{"detail": ...}` JSON，回退 `text()`，避免后端返回非 JSON 报错页导致崩溃。现有 `api()` 强制 JSON 解析，不能复用。

---

## 五、降级与错误矩阵

| 场景 | 行为 |
|---|---|
| 未配 MIMO Key | 麦克风、播放按钮、朗读开关**全部不渲染**，纯文字体验不变 |
| 浏览器不支持录音 | 特性检测拦截，提示换 Chrome/Edge，不进入录音流程 |
| 麦克风权限被拒 | 错误提示，打字输入不受影响 |
| ASR 超时（504）/ 上游错误（502） | 展示后端中文 `detail`，可重试或改打字 |
| TTS 超时 / 失败 | 跳过朗读，文本正常，播放按钮显示失败角标 |
| 文本超 500 字 | 后端截断前 500 字 + warning 日志，正常合成 |
| 非 wav / 超大音频 | 后端 400 / 413 拒绝，前端提示 |

核心原则：**语音是增强，不是关键路径。** 任何语音故障都退化为纯文字，不中断训练。

---

## 六、改动文件清单

**后端**
| 文件 | 改动 |
|---|---|
| `backend/app/config.py` | 新增 4 个 `mimo_*` 配置项 |
| `backend/app/services/voice.py` | 新建：`VoiceClient`（transcribe / synthesize / configured） |
| `backend/app/routers/voice.py` | 新建：`POST /voice/transcribe`、`POST /voice/speech` |
| `backend/app/schemas.py` | `MessageOut` 加 `id`；新增 `VoiceTranscribeIn` / `VoiceSpeechIn` |
| `backend/app/main.py` | 挂载 voice 路由；`/api/health` 加 `voice_configured` |
| `backend/app/smoke_test.py` | 回归：health 字段、503、magic number 校验、500 字截断 |

**配置与前端**
| 文件 | 改动 |
|---|---|
| `.env.example` | 加 `SALES_COACH_MIMO_API_KEY` 等占位 |
| `frontend/src/api.js` | 新增 `apiAudio()` |
| `frontend/src/audio.js` | 新建：`AudioRecorder` / `AudioPlayer`（含 WAV 编码） |
| `frontend/src/voice.jsx` | 新建：`MicButton` / `PlayButton` / `AutoReadToggle` |
| `frontend/src/App.jsx` | `Chat` 接线语音组件；`send()` 重构为可接收外部文本；传递 `voice_configured` |
| `frontend/src/styles.css` | 麦克风、录音脉冲、播放按钮四态、朗读开关样式 |

---

## 七、验证方式

1. **后端 smoke test**：扩展 `backend/app/smoke_test.py` 覆盖——`/api/health` 返回 `voice_configured`；未配 Key 时两个语音端点返回 503；transcribe 拒绝非 wav（magic number）；speech 超长截断。
2. **前端构建**：`npm run build` 通过。
3. **真 Key 手工 E2E**（`start-mvp.ps1`）：中文录音 → 自动发送 → 客户回复自动朗读 → 点重听 → 关闭朗读开关 → 打字链路不受影响。
4. **无 Key 降级**：不配 `SALES_COACH_MIMO_API_KEY`，确认语音 UI 完全不出现，文字训练闭环正常。

---

## 八、安全与入库边界

- MIMO API Key 只存服务端 `.env`，`.env.example` 仅占位，不进仓库。
- 语音端点全部要求登录（JWT），防止匿名滥用云端配额。
- 前端不持久化音频，只在内存缓存 Object URL，会话切换/卸载即释放。
