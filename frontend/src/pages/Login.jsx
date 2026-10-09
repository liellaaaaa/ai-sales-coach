import React, { useState } from "react";
import { api } from "../api";

export default function Login({ onLogin }) {
  const [form, setForm] = useState({ username: "sales", password: "123456" });
  const [error, setError] = useState("");
  async function submit(event) {
    event.preventDefault();
    try {
      const data = await api("/auth/login", { method: "POST", body: JSON.stringify(form) });
      localStorage.setItem("salesCoachToken", data.token);
      onLogin(data.user);
    } catch (err) {
      setError(err.message);
    }
  }
  return (
    <div className="login-page">
      <form className="login-card" onSubmit={submit}>
        <h1>销售陪练</h1>
        <p>演示账号：sales / admin，密码都是 123456。</p>
        <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
        <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        {error && <p className="error">{error}</p>}
        <button className="primary">登录</button>
      </form>
    </div>
  );
}
