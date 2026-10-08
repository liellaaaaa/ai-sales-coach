import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { api } from "./api";
import { OPPORTUNITY_MODE } from "./constants/training";
import { withSessionMeta } from "./utils/report";
import { sessionPayloadFromSession } from "./utils/training";
import Layout, { isMockRuntime } from "./components/Layout";
import Login from "./pages/Login";
import StartTraining from "./pages/StartTraining";
import Chat from "./pages/Chat";
import Report from "./pages/Report";
import History from "./pages/History";
import Dashboard from "./pages/Dashboard";
import Knowledge from "./pages/Knowledge";
import Profile from "./pages/Profile";
import ModelConfig from "./pages/ModelConfig";
import "./styles.css";

const LAST_SESSION_KEY = "salesCoachLastSessionId";

function App() {
  const [user, setUser] = useState(null);
  const [view, setView] = useState("start");
  const [railCollapsed, setRailCollapsed] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [sessions, setSessions] = useState([]);
  const [session, setSession] = useState(null);
  const [report, setReport] = useState(null);
  const [knowledge, setKnowledge] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [summary, setSummary] = useState(null);
  const [runtimeStatus, setRuntimeStatus] = useState(null);
  const [error, setError] = useState("");
  const [restoringSession, setRestoringSession] = useState(false);
  const [planDraft, setPlanDraft] = useState(null);
  const restoreLockRef = useRef(false);

  async function loadRuntimeStatus() {
    const status = await api("/health");
    setRuntimeStatus(status);
    return status;
  }

  async function loadSessions() {
    const sessionList = await api("/training/sessions");
    setSessions(sessionList);
    return sessionList;
  }

  async function loadAll() {
    // 并行拉取，单项失败不拖垮其它数据（否则历史/看板会整页空）
    const [sessionList, kb, docs, dash] = await Promise.allSettled([
      api("/training/sessions"),
      api("/knowledge"),
      api("/knowledge/documents"),
      api("/dashboard/summary"),
    ]);
    if (sessionList.status === "fulfilled") setSessions(sessionList.value);
    else throw sessionList.reason;
    if (kb.status === "fulfilled") setKnowledge(kb.value);
    if (docs.status === "fulfilled") setDocuments(docs.value);
    if (dash.status === "fulfilled") setSummary(dash.value);
  }

  /** 拉取完整会话（含 messages），并记住最近会话 */
  async function openSession(sessionId) {
    const full = await api(`/training/sessions/${sessionId}`);
    setSession(full);
    localStorage.setItem(LAST_SESSION_KEY, String(full.id));
    return full;
  }

  /** 进入对话页时回填：优先上次会话，否则取最近一条未完成/最新记录 */
  async function restoreChatSession() {
    if (session || restoreLockRef.current) return session;
    restoreLockRef.current = true;
    setRestoringSession(true);
    try {
      let list = sessions;
      if (!list.length) {
        try {
          list = await loadSessions();
        } catch {
          list = [];
        }
      }
      const savedId = Number(localStorage.getItem(LAST_SESSION_KEY));
      const preferred =
        list.find((item) => item.id === savedId) ||
        list.find((item) => item.status === "active") ||
        list[0];
      if (!preferred) return null;
      return await openSession(preferred.id);
    } catch (err) {
      setError(err.message);
      return null;
    } finally {
      restoreLockRef.current = false;
      setRestoringSession(false);
    }
  }

  useEffect(() => {
    let alive = true;
    loadRuntimeStatus()
      .then((status) => {
        if (alive) setRuntimeStatus(status);
      })
      .catch(() => {
        if (alive) setRuntimeStatus(null);
      });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    const token = localStorage.getItem("salesCoachToken");
    if (!token) return;
    api("/auth/me")
      .then((nextUser) => {
        setUser(nextUser);
        loadAll().catch((err) => setError(err.message));
      })
      .catch(() => localStorage.removeItem("salesCoachToken"));
  }, []);

  // 点进「训练对话」时若没有当前会话，从历史回填；点进「历史记录」时刷新列表
  useEffect(() => {
    if (!user) return;
    if (view === "chat" && !session) {
      void restoreChatSession();
    }
    if (view === "history") {
      loadSessions().catch((err) => setError(err.message));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, user]);

  if (!user) return <Login onLogin={(nextUser) => { setUser(nextUser); setView("start"); loadAll(); }} />;

  const navGroups = [
    { title: "训练流程", items: [["start", "开始训练", "新建训练"], ["chat", "训练对话", "当前对话"]] },
    { title: "复盘成长", items: [["report", "结果报告", "复盘方案"], ["history", "历史记录", "训练留档"], ["dashboard", "能力看板", "个人趋势"]] },
    {
      title: "知识资料",
      items: [["knowledge", user.role === "admin" ? "文档管理" : "文档查看", user.role === "admin" ? "SOP / 产品资料" : "只读资料"]],
    },
  ];
  const pageTitle = {
    ...Object.fromEntries(navGroups.flatMap((group) => group.items.map(([id, title]) => [id, title]))),
    profile: "个人资料",
    modelConfig: "模型配置",
  }[view];

  async function startSession(payload, mode, formContext) {
    setError("");
    const item = await api("/training/sessions", { method: "POST", body: JSON.stringify(payload) });
    setSession(item);
    localStorage.setItem(LAST_SESSION_KEY, String(item.id));
    if (mode === OPPORTUNITY_MODE) {
      const nextReport = await api(`/training/sessions/${item.id}/finish`, { method: "POST" });
      setReport(withSessionMeta(nextReport, item, formContext));
      setView("report");
    } else {
      setReport(null);
      setView("chat");
    }
    loadAll();
  }

  async function resetCurrentChat() {
    if (!session) return;
    const payload = sessionPayloadFromSession(session);
    const nextSession = await api("/training/sessions", { method: "POST", body: JSON.stringify(payload) });
    setSession(nextSession);
    localStorage.setItem(LAST_SESSION_KEY, String(nextSession.id));
    setReport(null);
    setView("chat");
    loadAll();
  }

  async function clearRecords() {
    await api("/training/sessions", { method: "DELETE" });
    localStorage.removeItem(LAST_SESSION_KEY);
    setSessions([]);
    setSession(null);
    setReport(null);
    loadAll();
  }

  function logout() {
    localStorage.removeItem("salesCoachToken");
    setAccountOpen(false);
    setSession(null);
    setReport(null);
    setView("start");
    setUser(null);
  }

  return (
    <Layout
      user={user}
      view={view}
      setView={setView}
      railCollapsed={railCollapsed}
      setRailCollapsed={setRailCollapsed}
      accountOpen={accountOpen}
      setAccountOpen={setAccountOpen}
      runtimeStatus={runtimeStatus}
      pageTitle={pageTitle}
      navGroups={navGroups}
      logout={logout}
    >
      {error && <div className="toast">{error}</div>}
      {view === "start" && (
        <StartTraining
          user={user}
          onError={setError}
          onStarted={startSession}
          recordCount={sessions.length}
          planDraft={planDraft}
          onPlanDraftApplied={() => setPlanDraft(null)}
        />
      )}
      {view === "chat" && <Chat session={session} restoring={restoringSession} voiceEnabled={runtimeStatus?.voice_configured === true} onError={setError} onSession={setSession} onReset={resetCurrentChat} onStartTraining={() => setView("start")} onReport={(nextReport) => { setReport(withSessionMeta(nextReport, session)); setView("report"); loadAll(); }} />}
      {view === "report" && (
        <Report
          report={report}
          session={session}
          onTrainFromPlan={(draft) => {
            setPlanDraft(draft);
            setView("start");
          }}
        />
      )}
      {view === "history" && (
        <History
          sessions={sessions}
          onClear={async () => { try { await clearRecords(); } catch (err) { setError(err.message); } }}
          onOpen={async (item) => {
            try {
              // 历史列表可能只有摘要，进详情前重新拉完整会话（含 messages）
              const full = await openSession(item.id);
              if (full.status === "completed") {
                const nextReport = await api(`/training/reports/${full.id}`);
                setReport(withSessionMeta(nextReport, full));
                setView("report");
              } else {
                setReport(null);
                setView("chat");
              }
            } catch (err) {
              setError(err.message);
            }
          }}
          onRetry={async (item) => {
            const nextSession = await api(`/training/sessions/${item.id}/retry`, { method: "POST" });
            setSession(nextSession);
            localStorage.setItem(LAST_SESSION_KEY, String(nextSession.id));
            setReport(null);
            setView("chat");
            loadAll();
          }}
        />
      )}
      {view === "dashboard" && <Dashboard summary={summary} />}
      {view === "knowledge" && <Knowledge key="knowledge" user={user} items={knowledge} documents={documents} onChanged={loadAll} onError={setError} />}
      {view === "profile" && <Profile user={user} onUser={setUser} onError={setError} />}
      {view === "modelConfig" && user.role === "admin" && <ModelConfig runtimeStatus={runtimeStatus} onSaved={loadRuntimeStatus} onError={setError} />}
    </Layout>
  );
}

createRoot(document.getElementById("root")).render(<App />);
