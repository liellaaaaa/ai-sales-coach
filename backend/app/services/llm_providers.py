"""LLM 传输协议适配：策略模式。

新增厂商时实现 ChatProvider，无需改 LLMClient 业务方法。
"""
from __future__ import annotations

import json
import logging
from typing import Any, AsyncGenerator, Protocol

import httpx

logger = logging.getLogger(__name__)


class ChatProvider(Protocol):
    """聊天补全协议：同步返回完整文本 / 异步流式返回片段。"""

    async def chat(self, messages: list[dict], model_id: str, api_key: str, max_tokens: int) -> str: ...

    def chat_stream(
        self, messages: list[dict], model_id: str, api_key: str, max_tokens: int
    ) -> AsyncGenerator[str, None]: ...


def _openai_messages(messages: list[dict]) -> list[dict]:
    converted = []
    for index, message in enumerate(messages):
        sender = message.get("sender_type")
        role = "assistant" if sender == "BOT" else "user"
        if sender == "SYSTEM" or (index == 0 and sender == "BOT"):
            role = "system"
        converted.append({"role": role, "content": message.get("text", "")})
    if converted and not any(message["role"] == "user" for message in converted):
        converted.append({"role": "user", "content": "请开始本次训练。"})
    return converted


def _anthropic_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    system_parts = []
    converted = []
    for index, message in enumerate(messages):
        sender = message.get("sender_type")
        text = message.get("text", "")
        if sender == "SYSTEM" or (index == 0 and sender == "BOT"):
            system_parts.append(text)
            continue
        role = "assistant" if sender == "BOT" else "user"
        converted.append({"role": role, "content": text})
    if not converted:
        converted.append({"role": "user", "content": "请开始。"})
    return "\n".join(system_parts), converted


def _strip_thinking(text: str) -> str:
    stripped = (text or "").strip()
    while stripped.startswith("<think>"):
        end = stripped.find("</think>")
        if end == -1:
            return stripped
        stripped = stripped[end + len("</think>") :].strip()
    return stripped


class OpenAICompatProvider:
    """OpenAI Chat Completions 兼容（DeepSeek / MiniMax / 多数网关）。"""

    def __init__(self, base_url: str):
        self.base_url = (base_url or "").rstrip("/")

    def _url(self) -> str:
        return (
            self.base_url
            if self.base_url.endswith("/chat/completions")
            else f"{self.base_url}/chat/completions"
        )

    async def chat(self, messages: list[dict], model_id: str, api_key: str, max_tokens: int) -> str:
        payload = {
            "model": model_id,
            "messages": _openai_messages(messages),
            "max_tokens": max_tokens,
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        body = await _post_json(self._url(), payload, headers)
        choices = body.get("choices") or []
        if not choices:
            return ""
        choice = choices[0]
        message = choice.get("message") or {}
        content = _strip_thinking(message.get("content") or choice.get("text") or "")
        if choice.get("finish_reason") == "length":
            logger.warning(
                "LLM 输出达到 max_tokens 上限被截断 (model=%s, max_tokens=%s)", model_id, max_tokens
            )
        return content

    async def chat_stream(
        self, messages: list[dict], model_id: str, api_key: str, max_tokens: int
    ) -> AsyncGenerator[str, None]:
        payload = {
            "model": model_id,
            "messages": _openai_messages(messages),
            "max_tokens": max_tokens,
            "stream": True,
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=15.0)) as client:
            async with client.stream("POST", self._url(), json=payload, headers=headers) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                        choices = obj.get("choices") or []
                        if choices:
                            delta = choices[0].get("delta") or {}
                            content = delta.get("content")
                            if content:
                                yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue


class AnthropicProvider:
    """Anthropic Messages API 兼容。"""

    def __init__(self, base_url: str):
        self.base_url = (base_url or "").rstrip("/")

    def _url(self) -> str:
        return self.base_url if self.base_url.endswith("/messages") else f"{self.base_url}/v1/messages"

    def _headers(self, api_key: str) -> dict[str, str]:
        return {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    async def chat(self, messages: list[dict], model_id: str, api_key: str, max_tokens: int) -> str:
        system, chat_messages = _anthropic_messages(messages)
        payload: dict[str, Any] = {
            "model": model_id,
            "max_tokens": max_tokens,
            "messages": chat_messages,
        }
        if system:
            payload["system"] = system
        body = await _post_json(self._url(), payload, self._headers(api_key))
        content = body.get("content") or []
        if isinstance(content, str):
            return content
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))

    async def chat_stream(
        self, messages: list[dict], model_id: str, api_key: str, max_tokens: int
    ) -> AsyncGenerator[str, None]:
        system, chat_messages = _anthropic_messages(messages)
        payload: dict[str, Any] = {
            "model": model_id,
            "max_tokens": max_tokens,
            "messages": chat_messages,
            "stream": True,
        }
        if system:
            payload["system"] = system
        async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=15.0)) as client:
            async with client.stream(
                "POST", self._url(), json=payload, headers=self._headers(api_key)
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        obj = json.loads(line[6:])
                        if obj.get("type") == "content_block_delta":
                            delta = obj.get("delta") or {}
                            text = delta.get("text")
                            if text:
                                yield text
                    except (json.JSONDecodeError, KeyError):
                        continue


class LegacyMiniMaxProvider:
    """旧版 MiniMax GroupId chatcompletion_v2。"""

    def __init__(self, group_id: str = ""):
        self.group_id = group_id or ""

    def _url(self) -> str:
        return f"https://api.minimax.chat/v1/text/chatcompletion_v2?GroupId={self.group_id}"

    async def chat(self, messages: list[dict], model_id: str, api_key: str, max_tokens: int) -> str:
        payload = {"model": model_id, "messages": messages, "tokens_to_generate": max_tokens}
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        body = await _post_json(self._url(), payload, headers)
        choices = body.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        return message.get("content") or message.get("text") or ""

    async def chat_stream(
        self, messages: list[dict], model_id: str, api_key: str, max_tokens: int
    ) -> AsyncGenerator[str, None]:
        result = await self.chat(messages, model_id, api_key, max_tokens)
        if result:
            yield result


def resolve_provider(base_url: str, group_id: str = "") -> ChatProvider:
    """按 base_url 选择协议实现（开闭：新厂商加分支或注册表）。"""
    if not base_url:
        return LegacyMiniMaxProvider(group_id)
    if "anthropic" in base_url.lower():
        return AnthropicProvider(base_url)
    return OpenAICompatProvider(base_url)


async def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    last_error = None
    async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=15.0)) as client:
        for _ in range(2):
            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as exc:
                last_error = exc
    raise last_error or httpx.HTTPError("LLM request failed")
