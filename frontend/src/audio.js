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

const PCM_SAMPLE_RATE = 24000;

/** 将 base64 编码的 PCM16LE 数据解码为 Float32Array */
function decodePcm16Base64(b64) {
  const raw = atob(b64);
  const int16 = new Int16Array(raw.length / 2);
  for (let i = 0; i < int16.length; i++) {
    const lo = raw.charCodeAt(i * 2);
    const hi = raw.charCodeAt(i * 2 + 1);
    int16[i] = (hi << 8) | lo;
  }
  const float32 = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) {
    float32[i] = int16[i] / 32768;
  }
  return float32;
}

/**
 * PCM16 流式播放器：接收 base64 编码的 PCM16 块，通过 Web Audio API 无缝拼接播放。
 */
export class PCMStreamPlayer {
  constructor() {
    this.ctx = null;
    this.nextTime = 0;
    this.sources = [];
    this.playing = false;
    this.onEnded = null;
    this._endedTimer = null;
  }

  _ensureContext() {
    if (!this.ctx || this.ctx.state === "closed") {
      this.ctx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: PCM_SAMPLE_RATE });
    }
    if (this.ctx.state === "suspended") {
      this.ctx.resume();
    }
    return this.ctx;
  }

  /** 追加一个 base64 PCM16 块并调度播放 */
  appendChunk(b64Data) {
    const ctx = this._ensureContext();
    const samples = decodePcm16Base64(b64Data);
    if (samples.length === 0) return;

    const buffer = ctx.createBuffer(1, samples.length, PCM_SAMPLE_RATE);
    buffer.getChannelData(0).set(samples);

    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);

    const now = ctx.currentTime;
    if (this.nextTime < now) {
      this.nextTime = now;
    }
    source.start(this.nextTime);
    this.nextTime += buffer.duration;
    this.sources.push(source);

    source.onended = () => {
      const idx = this.sources.indexOf(source);
      if (idx !== -1) this.sources.splice(idx, 1);
      this._checkAllEnded();
    };

    this.playing = true;
    // 清除之前的结束检测定时器
    if (this._endedTimer) {
      clearTimeout(this._endedTimer);
      this._endedTimer = null;
    }
  }

  /** 标记流结束，等待最后的 buffer 播完 */
  markStreamEnd() {
    // 给最后的 buffer 留出播放时间
    const remaining = this.nextTime - (this.ctx ? this.ctx.currentTime : 0);
    const waitMs = Math.max(remaining * 1000, 100);
    this._endedTimer = setTimeout(() => this._checkAllEnded(), waitMs + 200);
  }

  _checkAllEnded() {
    if (this.sources.length === 0 && this.playing) {
      this.playing = false;
      if (this._endedTimer) {
        clearTimeout(this._endedTimer);
        this._endedTimer = null;
      }
      this.onEnded?.();
    }
  }

  /** 停止播放 */
  stop() {
    this.playing = false;
    if (this._endedTimer) {
      clearTimeout(this._endedTimer);
      this._endedTimer = null;
    }
    for (const source of this.sources) {
      try { source.stop(); } catch { /* already stopped */ }
    }
    this.sources = [];
    this.nextTime = 0;
  }

  dispose() {
    this.stop();
    if (this.ctx && this.ctx.state !== "closed") {
      this.ctx.close();
    }
    this.ctx = null;
  }
}
