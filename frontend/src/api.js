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

/**
 * SSE 流式消费：逐事件回调。
 * handlers: { onToken(text), onDone({id, content}), onAudio(pcmBase64), onError(msg), onComplete() }
 */
export async function apiStream(path, body, handlers = {}) {
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
    const errBody = await response.json().catch(() => ({}));
    throw new Error(errBody.detail || "请求失败");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE 事件以 \n\n 分隔
    const parts = buffer.split("\n\n");
    buffer = parts.pop(); // 保留未完成的部分

    for (const part of parts) {
      if (!part.trim()) continue;
      let eventType = "message";
      let data = "";
      for (const line of part.split("\n")) {
        if (line.startsWith("event: ")) {
          eventType = line.slice(7);
        } else if (line.startsWith("data: ")) {
          data = line.slice(6);
        }
      }
      try {
        const parsed = data ? JSON.parse(data) : {};
        switch (eventType) {
          case "token":
            handlers.onToken?.(parsed.text || "");
            break;
          case "done":
            handlers.onDone?.(parsed);
            break;
          case "audio":
            handlers.onAudio?.(parsed.data || "");
            break;
          case "tts_error":
            console.warn("TTS error:", parsed.error);
            break;
          case "error":
            handlers.onError?.(parsed.error || "流式处理异常");
            break;
          case "complete":
            handlers.onComplete?.();
            break;
          default:
            break;
        }
      } catch {
        // 忽略解析错误
      }
    }
  }
  // 如果流结束但没收到 complete 事件，也触发 onComplete
  handlers.onComplete?.();
}
