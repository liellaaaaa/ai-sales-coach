const API_BASE = import.meta.env.VITE_API_BASE || "/api";

/** 401 时清理登录态并广播事件，由 App 统一跳转登录页 */
function notifyAuthExpired() {
  localStorage.removeItem("salesCoachToken");
  window.dispatchEvent(new CustomEvent("sales-coach-auth-expired"));
}

function throwHttpError(response, body) {
  if (response.status === 401) {
    notifyAuthExpired();
    throw new Error(body.detail || "登录已失效，请重新登录");
  }
  throw new Error(body.detail || "请求失败");
}

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
    throwHttpError(response, body);
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
    throwHttpError(response, body);
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
    if (response.status === 401) {
      notifyAuthExpired();
      throw new Error(detail || "登录已失效，请重新登录");
    }
    throw new Error(detail);
  }
  const buffer = await response.arrayBuffer();
  if (buffer.byteLength === 0) throw new Error("语音数据为空");
  return new Blob([buffer], { type: response.headers.get("content-type") || "audio/wav" });
}

function toAbortError(err) {
  if (err && err.name === "AbortError") return err;
  return new DOMException("Aborted", "AbortError");
}

/**
 * SSE 流式消费：逐事件回调。
 * handlers: { onToken(text), onDone({id, content}), onAudio(pcmBase64), onError(msg), onComplete() }
 * options: { signal } — AbortSignal，中断后抛出 AbortError，不触发 onError
 */
export async function apiStream(path, body, handlers = {}, options = {}) {
  const { signal } = options;
  const token = localStorage.getItem("salesCoachToken");

  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
      signal,
    });
  } catch (err) {
    if (signal?.aborted || err?.name === "AbortError") {
      console.debug("apiStream: 请求已中断（发起前）");
      throw toAbortError(err);
    }
    throw err;
  }
  if (!response.ok) {
    const errBody = await response.json().catch(() => ({}));
    throwHttpError(response, errBody);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
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
  } catch (err) {
    if (signal?.aborted || err?.name === "AbortError") {
      console.debug("apiStream: 流式请求已中断");
      try {
        reader.cancel();
      } catch {
        // 忽略 cancel 失败
      }
      throw toAbortError(err);
    }
    throw err;
  }
}
