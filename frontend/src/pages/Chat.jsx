import React, { useEffect, useMemo, useRef, useState } from "react";
import { api, apiAudio, apiStream } from "../api";
import { AudioPlayer, PCMStreamPlayer } from "../audio";
import { AutoReadToggle, MicButton, PlayButton } from "../voice";
import { Empty } from "../components/Layout";

const SPEAKER_META = {
  buyer: { label: "采购", className: "speaker-buyer" },
  tech: { label: "技术主管", className: "speaker-tech" },
  boss: { label: "厂长", className: "speaker-boss" },
};

function resolveSpeaker(speaker) {
  return SPEAKER_META[speaker] || SPEAKER_META.buyer;
}

function SpeakerBadge({ speaker }) {
  const meta = resolveSpeaker(speaker);
  return <span className={`speaker-badge ${meta.className}`}>{meta.label}</span>;
}

function hasText(value) {
  return Boolean((value || "").trim());
}

function FinishBar({ salesTurns, isFinishing, onFinish }) {
  const ready = salesTurns >= 3;
  return (
    <div className={`finish-bar ${ready ? "is-ready" : ""} ${isFinishing ? "is-loading" : ""}`}>
      <div className="finish-bar-copy">
        <b>{isFinishing ? "正在生成复盘" : ready ? `已对话 ${salesTurns} 轮，可生成报告` : `已对话 ${salesTurns} 轮`}</b>
        <span>{ready ? "已满足最小轮次，可结束本轮训练。" : "建议至少完成 3 轮，复盘依据更完整。"}</span>
      </div>
      <button type="button" className="primary finish-button" disabled={isFinishing || salesTurns < 1} onClick={onFinish}>
        {isFinishing ? "生成中" : "结束并生成报告"}
      </button>
    </div>
  );
}

function CustomerReplyWaitingPanel() {
  return (
    <div className="msg customer-waiting-msg">
      <span className="who">客户</span>
      <div className="bubble customer-waiting" role="status" aria-live="polite">
        <span className="typing-bubble" aria-hidden="true"><span /><span /><span /></span>
        <div>
          <b>客户正在生成回复</b>
          <p>正在结合你的回应和客户设定。</p>
        </div>
      </div>
    </div>
  );
}

function ReportGeneratingPanel({ salesTurns }) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const timer = window.setInterval(() => setElapsed((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return (
    <div className="report-generating" role="status" aria-live="polite">
      <div className="report-generation-head">
        <span className="report-pulse" aria-hidden="true"><i /><i /><i /></span>
        <div>
          <b>正在生成复盘报告</b>
          <p>已完成 {salesTurns} 轮回应，正在整理评分和复训建议。</p>
        </div>
        <em>{elapsed < 60 ? `${elapsed}s` : "即将完成"}</em>
      </div>
    </div>
  );
}

function BargeInBar({ onInterrupt }) {
  return (
    <div className="barge-in-bar" role="status">
      <span className="barge-in-hint">客户正在说话，可打断后直接发言</span>
      <button type="button" className="barge-in-button" onClick={onInterrupt}>
        打断说话
      </button>
    </div>
  );
}

export default function Chat({ session, restoring, onSession, onReport, onError, onStartTraining, voiceEnabled }) {
  const [text, setText] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isFinishing, setIsFinishing] = useState(false);
  const [isVoiceRecording, setIsVoiceRecording] = useState(false);
  const [autoRead, setAutoRead] = useState(() => localStorage.getItem("salesCoachAutoRead") !== "off");
  const [playback, setPlayback] = useState({ key: "", status: "idle" });
  const [streamingText, setStreamingText] = useState("");
  const [streamingActive, setStreamingActive] = useState(false);
  const [streamingSpeaker, setStreamingSpeaker] = useState("buyer");
  const playerRef = useRef(null);
  const pcmPlayerRef = useRef(null);
  const audioCache = useRef(new Map());
  const inputRef = useRef(null);
  const streamAbortRef = useRef(null);
  const micControlRef = useRef(null);
  const sendSeqRef = useRef(0);
  const sendingRef = useRef(false);
  const autoPlayedSessionRef = useRef(null);
  const salesTurns = useMemo(() => session?.messages?.filter((msg) => msg.role === "sales").length || 0, [session]);
  const visibleMessages = useMemo(
    () => (session?.messages || []).filter((msg) => hasText(msg.content)),
    [session?.messages]
  );

  useEffect(() => {
    playerRef.current = new AudioPlayer();
    pcmPlayerRef.current = new PCMStreamPlayer();
    audioCache.current = new Map();
    setPlayback({ key: "", status: "idle" });
    setStreamingText("");
    setStreamingActive(false);
    setStreamingSpeaker("buyer");
    return () => {
      streamAbortRef.current?.abort();
      streamAbortRef.current = null;
      playerRef.current?.dispose();
      pcmPlayerRef.current?.dispose();
    };
  }, [session?.id]);

  // 进入对话页时自动朗读最新一条客户回复
  useEffect(() => {
    if (!session?.id || !voiceEnabled || !autoRead) return;
    if (autoPlayedSessionRef.current === session.id) return;
    const messages = (session.messages || []).filter((msg) => hasText(msg.content));
    const lastIndex = messages.map((m) => m.role).lastIndexOf("customer");
    if (lastIndex < 0) return;
    autoPlayedSessionRef.current = session.id;
    void speakMessage(messages[lastIndex], lastIndex);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.id, voiceEnabled, autoRead]);

  function stopAllPlayback() {
    playerRef.current?.stop();
    pcmPlayerRef.current?.stop();
    if (pcmPlayerRef.current) pcmPlayerRef.current.onEnded = null;
    setPlayback({ key: "", status: "idle" });
  }

  function interruptClient() {
    const controller = streamAbortRef.current;
    if (controller) {
      streamAbortRef.current = null;
      try {
        controller.abort();
      } catch {
        // 忽略 abort 异常
      }
    }
    stopAllPlayback();
  }

  function toggleAutoRead(next) {
    setAutoRead(next);
    localStorage.setItem("salesCoachAutoRead", next ? "on" : "off");
  }

  function messageCacheKey(message, index) {
    const speaker = message.speaker || "buyer";
    return `${session.id}:${message.id ?? index}:${speaker}`;
  }

  async function speakMessage(message, index) {
    if (!playerRef.current) return;
    const speakText = (message.content || "").trim();
    if (!speakText) return;
    const key = messageCacheKey(message, index);
    if (playback.key === key && playback.status === "playing") {
      playerRef.current.stop();
      setPlayback({ key: "", status: "idle" });
      return;
    }
    stopAllPlayback();
    try {
      let blob = audioCache.current.get(key);
      if (!blob) {
        setPlayback({ key, status: "loading" });
        blob = await apiAudio("/voice/speech", {
          text: speakText,
          speaker: message.speaker || "buyer",
        });
        if (!blob || blob.size === 0) throw new Error("语音数据为空");
        audioCache.current.set(key, blob);
      }
      setPlayback({ key, status: "playing" });
      playerRef.current.playBlob(blob, () => {
        setPlayback((current) => (current.key === key ? { key: "", status: "idle" } : current));
      });
    } catch (err) {
      console.error("语音播放失败:", err);
      setPlayback({ key, status: "error" });
    }
  }

  if (!session) {
    if (restoring) return <Empty title="正在恢复对话" text="正在从历史记录加载最近一次训练…" />;
    return <Empty title="还没有训练" text="先从开始训练创建一次会话。" actionLabel="去开始训练" onAction={onStartTraining} />;
  }

  async function send(forcedContent) {
    const isForced = forcedContent != null;
    const content = (forcedContent ?? text).trim();
    if (!content || isFinishing) return;
    if (!isForced && sendingRef.current) return;

    interruptClient();

    const seq = ++sendSeqRef.current;
    const controller = new AbortController();
    streamAbortRef.current = controller;
    sendingRef.current = true;

    setText("");
    setIsSending(true);
    setStreamingText("");
    setStreamingActive(true);
    setStreamingSpeaker("buyer");
    onSession({ ...session, messages: [...session.messages, { role: "sales", content }] });

    try {
      let hasAudio = false;
      let doneSpeaker = null;

      await apiStream(`/training/sessions/${session.id}/stream`, { content }, {
        onToken(t) {
          if (seq !== sendSeqRef.current) return;
          setStreamingText((prev) => prev + t);
        },
        onDone(payload) {
          if (seq !== sendSeqRef.current) return;
          setStreamingActive(false);
          if (payload?.speaker) {
            doneSpeaker = payload.speaker;
            setStreamingSpeaker(payload.speaker);
          }
        },
        onAudio(pcmBase64) {
          if (seq !== sendSeqRef.current) return;
          if (!voiceEnabled || !autoRead) return;
          if (!hasAudio) {
            hasAudio = true;
            setPlayback({ key: `stream:${session.id}`, status: "playing" });
          }
          pcmPlayerRef.current?.appendChunk(pcmBase64);
        },
        onComplete() {
          if (seq !== sendSeqRef.current) return;
          if (hasAudio) {
            pcmPlayerRef.current?.markStreamEnd();
            pcmPlayerRef.current.onEnded = () => {
              setPlayback((current) =>
                current.key === `stream:${session.id}` ? { key: "", status: "idle" } : current
              );
            };
          }
        },
      }, { signal: controller.signal });

      if (seq !== sendSeqRef.current) return;

      const updated = await api(`/training/sessions/${session.id}`);
      const merged = doneSpeaker
        ? {
            ...updated,
            messages: (updated.messages || []).map((msg, idx, arr) => {
              if (msg.role !== "customer") return msg;
              const isLastCustomer = arr.slice(idx + 1).every((m) => m.role !== "customer");
              if (!isLastCustomer) return msg;
              return { ...msg, speaker: msg.speaker || doneSpeaker };
            }),
          }
        : updated;
      onSession(merged);
      setStreamingText("");
      setStreamingActive(false);
      if (!hasAudio && voiceEnabled && autoRead) {
        const candidates = (merged.messages || []).filter((msg) => hasText(msg.content));
        const lastIndex = candidates.map((m) => m.role).lastIndexOf("customer");
        if (lastIndex >= 0) void speakMessage(candidates[lastIndex], lastIndex);
      }
    } catch (err) {
      const aborted = err?.name === "AbortError" || controller.signal.aborted;
      if (aborted) {
        console.debug("流式回复已打断:", err?.message || err);
        if (seq === sendSeqRef.current) {
          setStreamingText("");
          setStreamingActive(false);
          try {
            const updated = await api(`/training/sessions/${session.id}`);
            if (seq === sendSeqRef.current) onSession(updated);
          } catch {
            // 忽略刷新失败
          }
        }
        return;
      }
      console.warn("流式端点失败，降级到非流式:", err.message);
      if (seq !== sendSeqRef.current) return;
      setStreamingText("");
      setStreamingActive(false);
      try {
        await api(`/training/sessions/${session.id}/messages`, { method: "POST", body: JSON.stringify({ content }) });
        const updated = await api(`/training/sessions/${session.id}`);
        if (seq !== sendSeqRef.current) return;
        onSession(updated);
        if (voiceEnabled && autoRead) {
          const candidates = (updated.messages || []).filter((msg) => hasText(msg.content));
          const lastIndex = candidates.map((m) => m.role).lastIndexOf("customer");
          if (lastIndex >= 0) speakMessage(candidates[lastIndex], lastIndex);
        }
      } catch (fallbackErr) {
        if (seq === sendSeqRef.current) onError(fallbackErr.message);
      }
    } finally {
      if (streamAbortRef.current === controller) streamAbortRef.current = null;
      if (seq === sendSeqRef.current) {
        sendingRef.current = false;
        setIsSending(false);
      }
    }
  }

  async function finish() {
    if (isFinishing) return;
    setIsFinishing(true);
    try {
      onReport(await api(`/training/sessions/${session.id}/finish`, { method: "POST" }));
    } catch (err) {
      onError(err.message);
      setIsFinishing(false);
    }
  }

  return (
    <section className="page chat-page">
      <div className="chat-shell">
        <FinishBar salesTurns={salesTurns} isFinishing={isFinishing} onFinish={finish} />
        <div className="chat-log">
          {visibleMessages.map((msg, index) => (
            <div key={msg.id ?? index} className={`msg ${msg.role === "sales" ? "sales" : ""}`}>
              <span className="who">
                {msg.role === "sales" ? "业务员" : "客户"}
                {msg.role === "customer" && <SpeakerBadge speaker={msg.speaker} />}
              </span>
              <div className="bubble-row">
                <div className="bubble">{msg.content}</div>
                {voiceEnabled && msg.role === "customer" && hasText(msg.content) && (
                  <PlayButton
                    status={playback.key === messageCacheKey(msg, index) ? playback.status : "idle"}
                    speaker={msg.speaker}
                    onClick={() => speakMessage(msg, index)}
                  />
                )}
              </div>
            </div>
          ))}
          {isSending && !streamingActive && <CustomerReplyWaitingPanel />}
          {streamingActive && streamingText && (
            <div className="msg">
              <span className="who">
                客户
                <SpeakerBadge speaker={streamingSpeaker} />
              </span>
              <div className="bubble-row">
                <div className="bubble streaming-bubble">{streamingText}<span className="streaming-cursor" /></div>
              </div>
            </div>
          )}
          {isFinishing && <ReportGeneratingPanel salesTurns={salesTurns} />}
        </div>
        <div className="chat-composer">
          {voiceEnabled && playback.status === "playing" && (
            <BargeInBar
              onInterrupt={() => {
                micControlRef.current?.startRecording();
              }}
            />
          )}
          <div className="composer-row">
            {voiceEnabled && (
              <MicButton
                disabled={isFinishing}
                onError={onError}
                onRecordingChange={setIsVoiceRecording}
                onResult={(recognized) => send(recognized)}
                onStopAllPlayback={interruptClient}
                controlRef={micControlRef}
              />
            )}
            <input
              ref={inputRef}
              value={text}
              disabled={isSending || isFinishing}
              onChange={(e) => setText(e.target.value)}
              placeholder={isSending ? "等待客户回复中" : isVoiceRecording ? "正在录音，松开发送" : "输入你的回应"}
              onKeyDown={(e) => { if (e.key === "Enter") send(); }}
            />
            <button className="send-button" disabled={!text.trim() || isSending || isFinishing} onClick={() => send()}>
              {isSending ? "发送中" : "发送"}
            </button>
          </div>
          {voiceEnabled && (
            <div className="composer-foot">
              <AutoReadToggle enabled={autoRead} onChange={toggleAutoRead} />
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
