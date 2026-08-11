import React, { useState } from "react";
import { api } from "../api";
import { roleName, accountInitial, rolePermissions } from "../components/Layout";

export default function Profile({ user, onUser, onError }) {
  const [form, setForm] = useState({ name: user.name || "", password: "" });
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const permissions = rolePermissions(user.role);

  async function submit(event) {
    event.preventDefault();
    setMessage("");
    onError("");

    const payload = { name: form.name.trim() };
    if (form.password.trim()) payload.password = form.password.trim();

    try {
      setSaving(true);
      const nextUser = await api("/auth/me", { method: "PATCH", body: JSON.stringify(payload) });
      onUser(nextUser);
      setForm({ name: nextUser.name || "", password: "" });
      setMessage("个人资料已保存");
    } catch (err) {
      onError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="page profile-page">
      <div className="hero profile-hero">
        <div className="intro">
          <span className="eyebrow">账号中心</span>
          <h3>个人资料</h3>
          <p>维护当前登录账号的基础信息。角色与权限由系统配置，暂不在这里直接修改。</p>
        </div>
        <div className="profile-identity-card">
          <span className="account-avatar profile-avatar">{accountInitial(user)}</span>
          <div>
            <b>{user.name}</b>
            <p>{user.username} · {roleName(user.role)}</p>
          </div>
        </div>
      </div>

      <div className="profile-grid">
        <form className="profile-card profile-editor" onSubmit={submit}>
          <header>
            <div>
              <span className="section-kicker">基础信息</span>
              <h4>账号资料</h4>
            </div>
            <span className="profile-status-pill">当前账号</span>
          </header>
          <div className="profile-form">
            <label className="profile-field">
              <span>登录账号</span>
              <input value={user.username} readOnly />
            </label>
            <label className="profile-field">
              <span>姓名</span>
              <input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="请输入姓名" />
            </label>
            <label className="profile-field">
              <span>新密码</span>
              <input
                type="password"
                value={form.password}
                onChange={(event) => setForm({ ...form, password: event.target.value })}
                placeholder="不修改可留空，至少 6 位"
              />
            </label>
          </div>
          <div className="profile-actions">
            {message && <span className="profile-success">{message}</span>}
            <button className="primary" type="submit" disabled={saving}>{saving ? "保存中..." : "保存资料"}</button>
          </div>
        </form>

        <section className="profile-card profile-permissions">
          <header>
            <div>
              <span className="section-kicker">权限范围</span>
              <h4>{roleName(user.role)}</h4>
            </div>
            <span className="profile-role-pill">{user.role}</span>
          </header>
          <div className="profile-meta">
            <div><span>用户 ID</span><b>{user.id}</b></div>
            <div><span>团队</span><b>{user.team_id ? `团队 ${user.team_id}` : "未绑定"}</b></div>
          </div>
          <div className="permission-list">
            {permissions.map((item) => (
              <div className="permission-item" key={item}>
                <span className="permission-dot" />
                <span>{item}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </section>
  );
}
