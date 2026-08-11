const API_BASE = import.meta.env.VITE_API_BASE || "/api";

export async function api(path, options = {}) {
  const token = localStorage.getItem("salesCoachToken");
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "请求失败");
  }
  return response.json();
}

export async function apiForm(path, formData) {
  const token = localStorage.getItem("salesCoachToken");
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: formData,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "请求失败");
  }
  return response.json();
}

export async function apiAudio(path, body) {
  const token = localStorage.getItem("salesCoachToken");
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    let detail = "请求失败";
    try {
      const parsed = await response.json();
      detail = parsed.detail || detail;
    } catch {
      const text = await response.text().catch(() => "");
      if (text) detail = text;
    }
    throw new Error(detail);
  }
  const buffer = await response.arrayBuffer();
  if (buffer.byteLength === 0) throw new Error("语音数据为空");
  return new Blob([buffer], { type: response.headers.get("content-type") || "audio/wav" });
}
