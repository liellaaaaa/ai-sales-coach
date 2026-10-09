import React, { useEffect, useState } from "react";
import { api } from "../api";

export default function ModelConfig({ runtimeStatus, onSaved, onError }) {
  const [config, setConfig] = useState(null);
  const [form, setForm] = useState({
    api_key: "",
    clear_api_key: false,
    base_url: "https://api.deepseek.com",
    model_name: "DeepSeek V4 Flash",
    model_id: "deepseek-v4-flash",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    let alive = true;
    api("/settings/llm")
      .then((data) => {
        if (!alive) return;
        setConfig(data);
        setForm({
          api_key: "",
          clear_api_key: false,
          base_url: data.base_url || "https://api.deepseek.com",
          model_name: data.model_name || "DeepSeek V4 Flash",
          model_id: data.model_id || "deepseek-v4-flash",
        });
      })
      .catch((err) => onError(err.message))
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [onError]);

  async function submit(event) {
    event.preventDefault();
    setMessage("");
    setTestResult(null);
    onError("");
    const payload = {
      clear_api_key: form.clear_api_key,
      base_url: form.base_url.trim(),
      model_name: form.model_name.trim(),
      model_id: form.model_id.trim(),
    };
    if (form.api_key.trim()) payload.api_key = form.api_key.trim();

    try {
      setSaving(true);
      const nextConfig = await api("/settings/llm", { method: "PATCH", body: JSON.stringify(payload) });
      setConfig(nextConfig);
      setForm({
        api_key: "",
        clear_api_key: false,
        base_url: nextConfig.base_url,
        model_name: nextConfig.model_name,
        model_id: nextConfig.model_id,
      });
      await onSaved?.();
      setMessage("模型配置已保存");
    } catch (err) {
      onError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function testConnection() {
    setMessage("");
    setTestResult(null);
    onError("");
    try {
      setTesting(true);
      setTestResult(await api("/settings/llm/test", { method: "POST" }));
      await onSaved?.();
    } catch (err) {
      onError(err.message);
    } finally {
      setTesting(false);
    }
  }

  return (
    <section className="page profile-page model-config-page">
      <div className="profile-identity-card model-status-card">
        <span className={`model-status-dot ${runtimeStatus?.llm_mode === "llm" ? "is-live" : ""}`} />
        <div>
          <b>{runtimeStatus?.llm_mode === "llm" ? "已接入模型" : "模拟模式"}</b>
          <p>{config?.model_id || "deepseek-v4-flash"}</p>
        </div>
      </div>

      <div className="profile-grid">
        <form className="profile-card profile-editor" onSubmit={submit}>
          <header>
            <div>
              <span className="section-kicker">DeepSeek</span>
              <h4>连接配置</h4>
            </div>
            <span className="profile-status-pill">{config?.llm_mode === "llm" ? "已启用" : "待配置"}</span>
          </header>
          {loading ? (
            <div className="empty-card">正在读取模型配置...</div>
          ) : (
            <>
              <div className="profile-form">
                <label className="profile-field full">
                  <span>API Key</span>
                  <input
                    type="password"
                    value={form.api_key}
                    onChange={(event) => setForm({ ...form, api_key: event.target.value, clear_api_key: false })}
                    placeholder={config?.has_api_key ? `${config.api_key_masked}，留空则不修改` : "输入 DeepSeek API Key"}
                  />
                </label>
                <label className="profile-field full">
                  <span>Base URL</span>
                  <input value={form.base_url} readOnly title="当前仅支持白名单内的接口地址" />
                </label>
                <label className="profile-field">
                  <span>模型名称</span>
                  <input value={form.model_name} onChange={(event) => setForm({ ...form, model_name: event.target.value })} />
                </label>
                <label className="profile-field">
                  <span>Model ID</span>
                  <input value={form.model_id} onChange={(event) => setForm({ ...form, model_id: event.target.value })} />
                </label>
              </div>
              {config?.has_api_key && (
                <label className="model-clear-key">
                  <input
                    type="checkbox"
                    checked={form.clear_api_key}
                    onChange={(event) => setForm({ ...form, clear_api_key: event.target.checked, api_key: event.target.checked ? "" : form.api_key })}
                  />
                  <span>清除已保存的 API Key</span>
                </label>
              )}
              <div className="profile-actions">
                {message && <span className="profile-success">{message}</span>}
                {testResult && (
                  <span className={`model-test-result ${testResult.ok ? "is-ok" : "is-failed"}`}>
                    {testResult.message} · {testResult.model_id} · {testResult.latency_ms}ms
                  </span>
                )}
                <button className="secondary" type="button" disabled={saving || testing || loading} onClick={testConnection}>
                  {testing ? "测试中..." : "测试连接"}
                </button>
                <button className="primary" type="submit" disabled={saving}>{saving ? "保存中..." : "保存配置"}</button>
              </div>
            </>
          )}
        </form>

        <section className="profile-card profile-permissions">
          <header>
            <div>
              <span className="section-kicker">当前状态</span>
              <h4>{config?.llm_mode === "llm" ? "真实模型" : "本地模拟"}</h4>
            </div>
            <span className="profile-role-pill">{config?.provider || "deepseek"}</span>
          </header>
          <div className="profile-meta model-meta">
            <div><span>API Key</span><b>{config?.has_api_key ? config.api_key_masked : "未配置"}</b></div>
            <div><span>接口模式</span><b>{config?.llm_configured ? "LLM" : "Mock"}</b></div>
            <div><span>Base URL</span><b>{config?.base_url || "https://api.deepseek.com"}</b></div>
            <div><span>Model ID</span><b>{config?.model_id || "deepseek-v4-flash"}</b></div>
          </div>
          <div className="permission-list">
            <div className="permission-item"><span className="permission-dot" /><span>默认地址：api.deepseek.com</span></div>
            <div className="permission-item"><span className="permission-dot" /><span>实际请求使用 Model ID</span></div>
            <div className="permission-item"><span className="permission-dot" /><span>未保存 API Key 时继续使用模拟回复</span></div>
          </div>
        </section>
      </div>
    </section>
  );
}
