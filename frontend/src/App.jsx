import React, { useEffect, useState } from "react";
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

  async function loadRuntimeStatus() {
    const status = await api("/health");
    setRuntimeStatus(status);
    return status;
  }

  async function loadAll() {
    const [sessionList, kb, docs, dash] = await Promise.all([
      api("/training/sessions"),
      api("/knowledge"),
      api("/knowledge/documents"),
      api("/dashboard/summary"),
    ]);
    setSessions(sessionList);
    setKnowledge(kb);
    setDocuments(docs);
    setSummary(dash);
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
        return loadAll();
      })
      .catch(() => localStorage.removeItem("salesCoachToken"));
  }, []);

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
    setReport(null);
    setView("chat");
    loadAll();
  }

  async function clearRecords() {
    await api("/training/sessions", { method: "DELETE" });
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
      {view === "start" && <StartTraining user={user} onError={setError} onStarted={startSession} recordCount={sessions.length} />}
      {view === "chat" && <Chat session={session} voiceEnabled={runtimeStatus?.voice_configured === true} onError={setError} onSession={setSession} onReset={resetCurrentChat} onStartTraining={() => setView("start")} onReport={(nextReport) => { setReport(withSessionMeta(nextReport, session)); setView("report"); loadAll(); }} />}
      {view === "report" && <Report report={report} />}
      {view === "history" && (
        <History
          sessions={sessions}
          onClear={async () => { try { await clearRecords(); } catch (err) { setError(err.message); } }}
          onOpen={async (item) => {
            setSession(item);
            if (item.status === "completed") {
              const nextReport = await api(`/training/reports/${item.id}`);
              setReport(withSessionMeta(nextReport, item));
              setView("report");
            } else {
              setReport(null);
              setView("chat");
            }
          }}
          onRetry={async (item) => {
            const nextSession = await api(`/training/sessions/${item.id}/retry`, { method: "POST" });
            setSession(nextSession);
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
