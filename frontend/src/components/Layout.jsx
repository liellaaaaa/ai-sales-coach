import React, { useState } from "react";

export function isMockRuntime(runtimeStatus) {
  return runtimeStatus?.llm_mode === "mock" || runtimeStatus?.llm_configured === false;
}

export function RuntimeModeBadge({ runtimeStatus }) {
  if (!isMockRuntime(runtimeStatus)) return null;
  return <span className="runtime-mode-badge">模拟模式</span>;
}

export function RuntimeModeNotice() {
  return (
    <div className="runtime-mode-notice" role="status" aria-live="polite">
      <b>当前为模拟模式</b>
      <span>未接入真实 LLM，客户回复和复盘报告会使用本地模拟结果。</span>
    </div>
  );
}

export function roleName(role) {
  return {
    sales: "业务员",
    admin: "管理员",
  }[role] || "用户";
}

export function accountInitial(user) {
  const text = user?.name || user?.username || "用户";
  return text.trim().slice(0, 1).toUpperCase();
}

export function rolePermissions(role) {
  return {
    sales: ["新建训练与客户对话", "管理自己的训练历史", "查看文档列表和资料片段"],
    admin: ["管理资料与训练记录", "维护账号权限", "配置系统基础能力"],
  }[role] || ["使用基础训练功能"];
}

export function Card({ title, children, className = "" }) {
  return <section className={`card ${className}`.trim()}><h3>{title}</h3>{children}</section>;
}

export function Empty({ title, text, actionLabel, onAction }) {
  return (
    <section className="empty">
      <h2>{title}</h2>
      <p>{text}</p>
      {actionLabel && onAction && (
        <button type="button" className="primary empty-action" onClick={onAction}>{actionLabel}</button>
      )}
    </section>
  );
}

export function input(label, key, form, setForm) {
  return <label>{label}<input value={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value })} /></label>;
}

export function select(label, key, form, setForm, options) {
  return <label>{label}<select value={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value })}>{options.map((item) => <option key={item}>{item}</option>)}</select></label>;
}

export function goalIcon(id) {
  const icons = {
    price: <><path d="M5 12h14"></path><path d="M8 8h8"></path><path d="M8 16h5"></path></>,
    terms: <><path d="M5 12h8"></path><path d="M13 7l5 5-5 5"></path><path d="M5 6h5"></path><path d="M5 18h5"></path></>,
    solution: <><path d="M9 4h6"></path><path d="M10 4v5l-4 7a3 3 0 0 0 2.6 4.5h6.8A3 3 0 0 0 18 16l-4-7V4"></path><path d="M8 15h8"></path></>,
    objection: <><path d="M12 3l8 4v5c0 4.5-3.2 8-8 10-4.8-2-8-5.5-8-10V7z"></path><path d="M9 12l2 2 4-4"></path></>,
    payment: <><path d="M4 7h16v10H4z"></path><path d="M4 10h16"></path><path d="M8 15h4"></path></>,
    retain: <><path d="M7 8a5 5 0 0 1 8.5-2.8L18 7"></path><path d="M18 4v3h-3"></path><path d="M17 16a5 5 0 0 1-8.5 2.8L6 17"></path><path d="M6 20v-3h3"></path></>,
    repurchase: <><path d="M4 12a8 8 0 0 1 13.5-5.8"></path><path d="M18 3v4h-4"></path><path d="M20 12a8 8 0 0 1-13.5 4.2"></path><path d="M6 21v-4h4"></path></>,
    lead: <><path d="M5 19l5-5"></path><path d="M14 4l6 6-8 8H6v-6z"></path><path d="M15 9l-6 6"></path></>,
    connect: <><path d="M8 12h8"></path><path d="M12 8v8"></path><path d="M7 7a5 5 0 0 1 7-3"></path><path d="M17 17a5 5 0 0 1-7 3"></path></>,
    visit: <><path d="M12 21s7-5.2 7-11a7 7 0 0 0-14 0c0 5.8 7 11 7 11z"></path><path d="M12 10h.01"></path></>,
    sample: <><path d="M8 4h8"></path><path d="M9 4v5l-3 8a3 3 0 0 0 2.8 4h6.4A3 3 0 0 0 18 17l-3-8V4"></path><path d="M8 15h8"></path></>,
    need: <><path d="M5 7h14"></path><path d="M5 12h10"></path><path d="M5 17h7"></path><path d="M16 15l3 3 3-3"></path></>,
    advance: <><path d="M5 12h10"></path><path d="M12 7l5 5-5 5"></path><path d="M19 6v12"></path></>,
    trial: <><path d="M5 5h14v14H5z"></path><path d="M8 12l2.5 2.5L16 9"></path></>,
    contract: <><path d="M7 4h10v16H7z"></path><path d="M10 8h4"></path><path d="M10 12h4"></path><path d="M10 16h2"></path></>,
    delivery: <><path d="M4 7h10v8H4z"></path><path d="M14 10h3l3 3v2h-6z"></path><path d="M7 18h.01"></path><path d="M17 18h.01"></path></>,
    stalled: <><path d="M5 12h8"></path><path d="M13 7l5 5-5 5"></path><path d="M5 6h5"></path><path d="M5 18h5"></path></>,
    technical: <><path d="M9 4h6"></path><path d="M10 4v5l-4 7a3 3 0 0 0 2.6 4.5h6.8A3 3 0 0 0 18 16l-4-7V4"></path><path d="M8 15h8"></path></>,
    retention: <><path d="M7 8a5 5 0 0 1 8.5-2.8L18 7"></path><path d="M18 4v3h-3"></path><path d="M17 16a5 5 0 0 1-8.5 2.8L6 17"></path><path d="M6 20v-3h3"></path></>,
    stakeholder: <><path d="M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"></path><path d="M3.5 19a4.5 4.5 0 0 1 9 0"></path><path d="M17 9a2.5 2.5 0 1 0 0-5"></path><path d="M15 19h5"></path></>,
    report: <><path d="M6 4h9l3 3v13H6z"></path><path d="M14 4v4h4"></path><path d="M9 13h6"></path><path d="M9 17h4"></path></>,
    service: <><path d="M12 3l7 4v5c0 4-3 7-7 9-4-2-7-5-7-9V7z"></path><path d="M9 12l2 2 4-5"></path></>,
  };
  return <svg viewBox="0 0 24 24" aria-hidden="true">{icons[id] || icons.price}</svg>;
}

export function navIcon(id) {
  const icons = {
    start: <><path d="M4 7h16"></path><path d="M4 12h16"></path><path d="M4 17h10"></path></>,
    chat: <><path d="M5 6h14v9H9l-4 4z"></path><path d="M8 9h8"></path></>,
    report: <><path d="M5 19V5"></path><path d="M5 19h14"></path><path d="M9 15v-4"></path><path d="M13 15V8"></path><path d="M17 15v-6"></path></>,
    history: <><path d="M5 5h14v14H5z"></path><path d="M8 9h8"></path><path d="M8 13h5"></path></>,
    dashboard: <><path d="M4 13h6V5H4z"></path><path d="M14 19h6V5h-6z"></path><path d="M4 19h6v-3H4z"></path></>,
    knowledge: <><path d="M6 4h9l3 3v13H6z"></path><path d="M14 4v4h4"></path><path d="M9 12h6"></path><path d="M9 16h6"></path></>,
    more: <><circle cx="6" cy="12" r="1.2"></circle><circle cx="12" cy="12" r="1.2"></circle><circle cx="18" cy="12" r="1.2"></circle></>,
    profile: <><circle cx="12" cy="8" r="3.2"></circle><path d="M5.5 19a6.5 6.5 0 0 1 13 0"></path></>,
  };
  return <svg viewBox="0 0 24 24" aria-hidden="true">{icons[id]}</svg>;
}

const MOBILE_TABS = [
  ["start", "训练"],
  ["chat", "对话"],
  ["report", "报告"],
  ["history", "历史"],
];

export default function Layout({
  user,
  view,
  setView,
  accountOpen,
  setAccountOpen,
  runtimeStatus,
  pageTitle,
  logout,
  children,
}) {
  const [moreOpen, setMoreOpen] = useState(false);
  const secondaryViews = [
    ["dashboard", "能力看板", "个人趋势"],
    ["knowledge", user.role === "admin" ? "文档管理" : "文档查看", "SOP / 产品资料"],
    ["profile", "个人资料", "账号信息与权限"],
    ...(user.role === "admin" ? [["modelConfig", "模型配置", "LLM / API Key"]] : []),
  ];
  const moreActive = secondaryViews.some(([id]) => id === view);

  function goView(id) {
    setMoreOpen(false);
    setView(id);
  }

  return (
    <div className={`app app-shell ${view === "chat" ? "view-chat" : ""}`}>
      <header className="topbar">
        <div className="topbar-title">
          <h2>{pageTitle}</h2>
          <RuntimeModeBadge runtimeStatus={runtimeStatus} />
        </div>
        <div className="account-menu">
          <button className="account-trigger" type="button" aria-haspopup="menu" aria-expanded={accountOpen} onClick={() => setAccountOpen((value) => !value)}>
            <span className="account-avatar">{accountInitial(user)}</span>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 10l5 5 5-5"></path></svg>
          </button>
          {accountOpen && (
            <div className="account-popover" role="menu">
              <div className="account-profile">
                <span className="account-avatar large">{accountInitial(user)}</span>
                <div><b>{user.name}</b><p>{user.username} · {roleName(user.role)}</p></div>
              </div>
              <button
                className="account-row"
                type="button"
                role="menuitem"
                onClick={() => {
                  setAccountOpen(false);
                  setView("profile");
                }}
              >
                <span>个人资料</span>
                <small>账号信息与权限</small>
              </button>
              {user.role === "admin" && (
                <button
                  className="account-row"
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setAccountOpen(false);
                    setView("modelConfig");
                  }}
                >
                  <span>模型配置</span>
                  <small>LLM / API Key</small>
                </button>
              )}
              <button className="account-row danger" type="button" role="menuitem" onClick={logout}>
                <span>退出登录</span>
                <small>返回登录入口</small>
              </button>
            </div>
          )}
        </div>
      </header>

      <main className="workspace">
        {isMockRuntime(runtimeStatus) && <RuntimeModeNotice />}
        {children}
      </main>

      <nav className="bottom-tabs" aria-label="底部导航">
        {MOBILE_TABS.map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={`bottom-tab ${view === id ? "active" : ""}`}
            onClick={() => goView(id)}
          >
            <span className="bottom-tab-icon">{navIcon(id)}</span>
            <span>{label}</span>
          </button>
        ))}
        <button
          type="button"
          className={`bottom-tab ${moreActive || moreOpen ? "active" : ""}`}
          onClick={() => setMoreOpen((value) => !value)}
          aria-expanded={moreOpen}
        >
          <span className="bottom-tab-icon">{navIcon("more")}</span>
          <span>更多</span>
        </button>
      </nav>

      {moreOpen && (
        <>
          <button
            type="button"
            className="more-sheet-backdrop"
            aria-label="关闭更多菜单"
            onClick={() => setMoreOpen(false)}
          />
          <div className="more-sheet" role="dialog" aria-label="更多功能">
            <div className="more-sheet-handle" aria-hidden="true" />
            <p className="more-sheet-title">更多</p>
            {secondaryViews.map(([id, title, sub]) => (
              <button
                key={id}
                type="button"
                className={`more-row ${view === id ? "active" : ""}`}
                onClick={() => goView(id)}
              >
                <span className="more-row-icon">{navIcon(id)}</span>
                <span className="more-row-copy">
                  <b>{title}</b>
                  <small>{sub}</small>
                </span>
              </button>
            ))}
            <button type="button" className="more-row danger" onClick={() => { setMoreOpen(false); logout(); }}>
              <span className="more-row-icon">{navIcon("profile")}</span>
              <span className="more-row-copy">
                <b>退出登录</b>
                <small>返回登录入口</small>
              </span>
            </button>
          </div>
        </>
      )}
    </div>
  );
}
