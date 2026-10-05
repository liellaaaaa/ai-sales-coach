import React, { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { AudioRecorder, RECORDER_STATES, blobToBase64 } from "./audio";

const TAP_MAX_MS = 280;
const TAP_MAX_MOVE_PX = 14;

export function MicButton({
  disabled,
  onResult,
  onError,
  onRecordingChange,
  onStopAllPlayback,
  controlRef,
}) {
  const recorderRef = useRef(null);
  const deliverRef = useRef(() => {});
  const callbacksRef = useRef({ onResult, onError, onRecordingChange, onStopAllPlayback });
  callbacksRef.current = { onResult, onError, onRecordingChange, onStopAllPlayback };
  const [state, setState] = useState(RECORDER_STATES.idle);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [isHoldMode, setIsHoldMode] = useState(false);
  const [supportError] = useState(() => AudioRecorder.supportDetail());
  const transcribingRef = useRef(false);
  const startPromiseRef = useRef(null);
  const ignoreClickRef = useRef(false);
  const pressRef = useRef({
    active: false,
    pointerId: null,
    startTs: 0,
    startY: 0,
    startedOnDown: false,
  });

  async function deliver(wavBlob) {
    transcribingRef.current = true;
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
      transcribingRef.current = false;
      setIsTranscribing(false);
      setIsHoldMode(false);
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
        setIsHoldMode(false);
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

  async function beginRecording() {
    const recorder = recorderRef.current;
    if (!recorder || transcribingRef.current || supportError) return;
    if (
      recorder.state === RECORDER_STATES.recording ||
      recorder.state === RECORDER_STATES.warning
    ) {
      return;
    }
    // 开录前先打断客户播报/流式（barge-in）
    try {
      callbacksRef.current.onStopAllPlayback?.();
    } catch {
      // 忽略打断失败
    }
    try {
      const pending = recorder.start();
      startPromiseRef.current = pending;
      await pending;
    } catch (err) {
      callbacksRef.current.onError(err.message || "无法启动录音");
    } finally {
      startPromiseRef.current = null;
    }
  }

  async function endRecordingAndSend() {
    const recorder = recorderRef.current;
    if (!recorder || transcribingRef.current) return;
    setIsHoldMode(false);
    if (startPromiseRef.current) {
      try {
        await startPromiseRef.current;
      } catch {
        return;
      }
    }
    if (
      recorder.state !== RECORDER_STATES.recording &&
      recorder.state !== RECORDER_STATES.warning
    ) {
      return;
    }
    try {
      const wavBlob = await recorder.stop();
      if (wavBlob) await deliver(wavBlob);
    } catch (err) {
      callbacksRef.current.onError(err.message || "录音失败，请重试");
    }
  }

  useEffect(() => {
    if (!controlRef) return undefined;
    controlRef.current = {
      startRecording: () => beginRecording(),
      stopAndSend: () => endRecordingAndSend(),
    };
    return () => {
      controlRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handlePointerDown(event) {
    if (disabled || isTranscribing || supportError) return;
    if (event.button != null && event.button !== 0) return;
    ignoreClickRef.current = true;
    event.preventDefault();
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      // 某些环境不支持 pointer capture
    }

    const recorder = recorderRef.current;
    if (!recorder) return;

    pressRef.current = {
      active: true,
      pointerId: event.pointerId,
      startTs: Date.now(),
      startY: event.clientY,
      startedOnDown: !recording,
    };

    if (recording) {
      // 已在录音（轻点切换模式）：本次按下抬起时结束并发送
      return;
    }

    setIsHoldMode(true);
    void beginRecording();
  }

  function handlePointerUp(event) {
    const press = pressRef.current;
    if (!press.active) return;
    pressRef.current = {
      active: false,
      pointerId: null,
      startTs: 0,
      startY: 0,
      startedOnDown: false,
    };

    const duration = Date.now() - press.startTs;
    const moved = Math.abs(event.clientY - press.startY) > TAP_MAX_MOVE_PX;
    const isShortTap = !moved && duration < TAP_MAX_MS;

    // 本次按下才启动录音，且是短按 → 转为轻点切换模式，继续录音
    if (press.startedOnDown && isShortTap) {
      setIsHoldMode(false);
      return;
    }

    void endRecordingAndSend();
  }

  function handlePointerCancel() {
    const press = pressRef.current;
    if (!press.active) return;
    pressRef.current = {
      active: false,
      pointerId: null,
      startTs: 0,
      startY: 0,
      startedOnDown: false,
    };
    setIsHoldMode(false);
    void endRecordingAndSend();
  }

  function handleClick(event) {
    if (ignoreClickRef.current) {
      ignoreClickRef.current = false;
      return;
    }
    // 键盘激活（无 pointer 序列）：切换开始/结束
    if (disabled || isTranscribing || supportError) return;
    if (recording) {
      void endRecordingAndSend();
      return;
    }
    setIsHoldMode(false);
    void beginRecording();
  }

  const label = supportError
    ? "不支持录音"
    : isTranscribing
      ? "识别中…"
      : recording
        ? isHoldMode
          ? "松开发送"
          : state === RECORDER_STATES.warning
            ? "即将到限，点击结束"
            : "点击结束发送"
        : "语音输入";

  const title = supportError
    ? supportError
    : isTranscribing
      ? "识别中，请稍候"
      : recording
        ? isHoldMode
          ? "松开发送，也可轻点结束"
          : "点击结束并发送"
        : "按住说话，松开发送；轻点开始，再次点击结束";

  if (supportError) {
    return (
      <button
        type="button"
        className="mic-button is-unsupported"
        disabled
        title={supportError}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M12 4a3 3 0 0 1 3 3v5a3 3 0 0 1-6 0V7a3 3 0 0 1 3-3z"></path>
          <path d="M6 11a6 6 0 0 0 12 0"></path>
          <path d="M12 17v3"></path>
          <line x1="4" y1="4" x2="20" y2="20" stroke="currentColor" strokeWidth="2" />
        </svg>
        <span>{label}</span>
      </button>
    );
  }

  return (
    <button
      type="button"
      className={`mic-button ${recording ? "is-recording" : ""} ${isHoldMode && recording ? "is-holding" : ""} ${state === RECORDER_STATES.warning ? "is-warning" : ""}`}
      disabled={disabled || isTranscribing}
      onClick={handleClick}
      onPointerDown={handlePointerDown}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerCancel}
      onContextMenu={(event) => event.preventDefault()}
      title={title}
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

const SPEAKER_TITLES = {
  buyer: "采购",
  tech: "技术主管",
  boss: "厂长",
};

export function PlayButton({ status, onClick, speaker }) {
  const speakerLabel = SPEAKER_TITLES[speaker] || SPEAKER_TITLES.buyer;
  const title =
    status === "loading"
      ? "正在合成语音"
      : status === "playing"
        ? "停止播放"
        : status === "error"
          ? "语音合成失败，点击重试"
          : `播放这条回复（${speakerLabel}音色）`;
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
