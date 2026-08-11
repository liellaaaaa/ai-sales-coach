import React, { useEffect, useMemo, useRef, useState } from "react";
import { api, apiAudio, apiStream } from "../api";
import { AudioPlayer, PCMStreamPlayer } from "../audio";
import { AutoReadToggle, MicButton, PlayButton } from "../voice";
import { standardReplies } from "../constants/training";
import { Empty } from "../components/Layout";

function ReviewReadinessPanel({ salesTurns, isFinishing, onReset, onFinish }) {
  const ready = salesTurns >= 3;
  const remaining = Math.max(3 - salesTurns, 0);
  const title = isFinishing ? "正在生成复盘" : ready ? "可继续对话或进入复盘" : "建议再补一轮";
  const detail = isFinishing
    ? "系统正在整理对话评分、关键话术、知识库依据和复训任务。"
    : ready
      ? "已满足最小轮次，你可以继续补充对话，也可以结束并生成内容复盘。"
      : `当前已完成 ${salesTurns} 轮，建议至少再完成 ${remaining} 轮，让复盘依据更完整。`;
  return (
    <div className={`review-readiness ${ready ? "is-ready" : ""} ${isFinishing ? "is-loading" : ""}`}>
      <div>
        <span className="review-readiness-label">复盘准备</span>
        <b>{title}</b>
        <p>{detail}</p>
      </div>
      <div className="review-readiness-meter" aria-label={`已完成 ${salesTurns} 轮，建议至少 3 轮`}>
        {[0, 1, 2].map((index) => <i key={index} className={index < Math.min(salesTurns, 3) ? "filled" : ""} />)}
      </div>
      {ready ? (
        <div className="review-readiness-actions">
          <button className="secondary finish-button" disabled={isFinishing} onClick={onReset}>重新对话</button>
          <button className="primary finish-button" disabled={isFinishing} onClick={onFinish}>{isFinishing ? "生成报告中" : "结束并生成报告"}</button>
        </div>
      ) : <span className="review-readiness-pending">完成 3 轮后可生成复盘报告</span>}
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
          <p>正在结合你的回应、客户设定和当前训练目标。</p>
        </div>
      </div>
    </div>
  );
}

function SuggestionLoadingPanel() {
  return (
    <div className="suggestion-loading" role="status" aria-live="polite">
      <div className="suggestion-loading-head">
        <span className="suggestion-pulse" aria-hidden="true"><i /><i /><i /></span>
        <div>
          <b>正在生成参考回复</b>
          <p>正在结合客户最新反馈和训练目标。</p>
        </div>
      </div>
      <div className="suggestion-loading-lines" aria-hidden="true">
        <i /><i /><i />
      </div>
    </div>
  );
}

function ReportGeneratingPanel({ salesTurns }) {
  const [elapsed, setElapsed] = useState(0);
  const steps = [
    ["对话梳理", "提取客户异议和业务员关键回应"],
    ["SOP 对照", "匹配知识库依据和风险话术"],
    ["评分生成", "整理能力评分、金句和复训任务"],
  ];
  const activeIndex = Math.min(Math.floor(elapsed / 4), steps.length - 1);
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
          <p>已完成 {salesTurns} 轮回应，正在把本轮对话整理成评分、依据和复训任务。</p>
        </div>
        <em>{elapsed < 60 ? `${elapsed}s` : "即将完成"}</em>
      </div>
      <div className="report-stepper">
        {steps.map(([title, text], index) => (
          <div key={title} className={`report-step ${index < activeIndex ? "done" : ""} ${index === activeIndex ? "active" : ""}`}>
            <div className="report-step-main">
              <span>{index + 1}</span>
              <div><b>{title}</b><small>{text}</small></div>
            </div>
            <div className="report-step-preview" aria-hidden="true"><i /><i /><i /></div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Chat({ session, onSession, onReport, onError, onReset, voiceEnabled }) {
  const [text, setText] = useState("");
  const [showExample, setShowExample] = useState(false);
  const [suggestion, setSuggestion] = useState(null);
  const [isSuggesting, setIsSuggesting] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [isFinishing, setIsFinishing] = useState(false);
  const [isVoiceRecording, setIsVoiceRecording] = useState(false);
  const [autoRead, setAutoRead] = useState(() => localStorage.getItem("salesCoachAutoRead") !== "off");
  const [playback, setPlayback] = useState({ key: "", status: "idle" });
  const [streamingText, setStreamingText] = useState("");
  const [streamingActive, setStreamingActive] = useState(false);
  const playerRef = useRef(null);
  const pcmPlayerRef = useRef(null);
  const audioCache = useRef(new Map());
  const inputRef = useRef(null);
  const suggestionRef = useRef(null);
  const salesTurns = useMemo(() => session?.messages?.filter((msg) => msg.role === "sales").length || 0, [session]);
  const exampleReply = standardReplies[session?.goal] || standardReplies["价格异议"];

  useEffect(() => {
    playerRef.current = new AudioPlayer();
    pcmPlayerRef.current = new PCMStreamPlayer();
    audioCache.current = new Map();
    setPlayback({ key: "", status: "idle" });
    setStreamingText("");
    setStreamingActive(false);
    return () => {
      playerRef.current?.dispose();
      pcmPlayerRef.current?.dispose();
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

  useEffect(() => {
    if (!showExample) return undefined;
    function handlePointerDown(event) {
      if (suggestionRef.current?.contains(event.target)) return;
      setShowExample(false);
    }
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [showExample]);

  if (!session) return <Empty title="还没有训练" text="先从开始训练创建一次会话。" />;

  async function send(forcedContent) {
    const content = (forcedContent ?? text).trim();
    if (!content || isSending || isFinishing) return;
    setText("");
    setSuggestion(null);
    setShowExample(false);
    setIsSending(true);
    setStreamingText("");
    setStreamingActive(true);
    playerRef.current?.stop();
    pcmPlayerRef.current?.stop();
    setPlayback({ key: "", status: "idle" });
    onSession({ ...session, messages: [...session.messages, { role: "sales", content }] });

    try {
      let finalMessage = null;
      let hasAudio = false;

      await apiStream(`/training/sessions/${session.id}/stream`, { content }, {
        onToken(text) {
          setStreamingText((prev) => prev + text);
        },
        onDone(msg) {
          finalMessage = msg;
          setStreamingActive(false);
        },
        onAudio(pcmBase64) {
          if (!voiceEnabled || !autoRead) return;
          if (!hasAudio) {
            hasAudio = true;
            setPlayback({ key: `stream:${session.id}`, status: "playing" });
          }
          pcmPlayerRef.current?.appendChunk(pcmBase64);
        },
        onComplete() {
          if (hasAudio) {
            pcmPlayerRef.current?.markStreamEnd();
            pcmPlayerRef.current.onEnded = () => {
              setPlayback({ key: "", status: "idle" });
            };
          }
        },
      });

      const updated = await api(`/training/sessions/${session.id}`);
      onSession(updated);
      setStreamingText("");
      setStreamingActive(false);
    } catch (err) {
      onError(err.message);
      setStreamingText("");
      setStreamingActive(false);
    } finally {
      setIsSending(false);
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

  async function toggleSuggestion() {
    const nextOpen = !showExample;
    setShowExample(nextOpen);
    if (!nextOpen || suggestion || isSuggesting) return;
    setIsSuggesting(true);
    try {
      setSuggestion(await api(`/training/sessions/${session.id}/suggestion`, { method: "POST" }));
    } catch (err) {
      onError(err.message);
    } finally {
      setIsSuggesting(false);
    }
  }

  return (
    <section className="page knowledge-page">
      <div className="hero">
        <div className="intro"><span className="eyebrow">客户情景陪练</span><h3>{session.goal}：{session.customer_name}</h3><p className="hint">{session.stage} / {session.training_type} / {session.customer_type}</p></div>
        <div className="metric-card"><span className="small">业务员轮次</span><strong>{salesTurns}</strong><p className="small">{salesTurns >= 3 ? "已满足验收轮次" : "建议至少 3 轮"}</p></div>
      </div>
      <div className="chat">
        <div className="chat-log">
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
          {isSending && !streamingActive && <CustomerReplyWaitingPanel />}
          {streamingActive && streamingText && (
            <div className="msg">
              <span className="who">客户</span>
              <div className="bubble-row">
                <div className="bubble streaming-bubble">{streamingText}<span className="streaming-cursor" /></div>
              </div>
            </div>
          )}
        </div>
        <div className="chat-actions">
          <div className="composer-tools">
            <span>{streamingActive ? "客户正在回复..." : isSending ? "客户正在思考你的回应..." : salesTurns >= 3 ? "已满足验收轮次，可以进入复盘。" : "建议至少完成 3 轮回应。"}</span>
            {voiceEnabled && <AutoReadToggle enabled={autoRead} onChange={toggleAutoRead} />}
            <div ref={suggestionRef} className={`standard-preview ai-suggestion ${showExample ? "open" : ""}`}>
              <button type="button" onClick={toggleSuggestion} aria-expanded={showExample} disabled={isSending || isFinishing}>{isSuggesting ? "生成中" : "AI推荐回复"}</button>
              <div className="standard-popover ai-suggestion-popover">
                <div className="suggestion-popover-head">
                  <span className="suggestion-label">AI 推荐回复</span>
                  <button className="suggestion-close" type="button" aria-label="关闭推荐回复" onClick={() => setShowExample(false)}>×</button>
                </div>
                {isSuggesting ? (
                  <SuggestionLoadingPanel />
                ) : (
                  <>
                    <p>{suggestion?.content || exampleReply}</p>
                    <small>{suggestion?.notice || "AI 推荐回复仅用于训练参考，并不完全适用于实际业务场景。"}</small>
                  </>
                )}
              </div>
            </div>
          </div>
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
          {isFinishing && <ReportGeneratingPanel salesTurns={salesTurns} />}
        </div>
      </div>
      <ReviewReadinessPanel salesTurns={salesTurns} isFinishing={isFinishing} onReset={onReset} onFinish={finish} />
    </section>
  );
}
