"""LLM Provider 策略单测。"""
from app.services.llm_providers import (
    AnthropicProvider,
    LegacyMiniMaxProvider,
    OpenAICompatProvider,
    _anthropic_messages,
    _openai_messages,
    _strip_thinking,
    resolve_provider,
)


def test_resolve_openai_compat():
    provider = resolve_provider("https://api.deepseek.com")
    assert isinstance(provider, OpenAICompatProvider)
    assert provider._url().endswith("/chat/completions")


def test_resolve_anthropic():
    provider = resolve_provider("https://api.anthropic.com")
    assert isinstance(provider, AnthropicProvider)
    assert provider._url().endswith("/v1/messages")


def test_resolve_legacy_when_empty_base():
    provider = resolve_provider("", group_id="g1")
    assert isinstance(provider, LegacyMiniMaxProvider)
    assert "GroupId=g1" in provider._url()


def test_openai_messages_system_first():
    converted = _openai_messages([{"sender_type": "BOT", "text": "sys"}, {"sender_type": "USER", "text": "hi"}])
    assert converted[0]["role"] == "system"
    assert converted[1]["role"] == "user"


def test_anthropic_messages_split_system():
    system, chat = _anthropic_messages(
        [{"sender_type": "SYSTEM", "text": "sys"}, {"sender_type": "USER", "text": "hi"}]
    )
    assert system == "sys"
    assert chat == [{"role": "user", "content": "hi"}]


def test_strip_thinking():
    assert _strip_thinking("<think>hidden</think>\nOK") == "OK"
    assert _strip_thinking("plain") == "plain"
