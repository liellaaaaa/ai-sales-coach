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
