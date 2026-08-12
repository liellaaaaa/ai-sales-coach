import base64
import os
import tempfile
from pathlib import Path

db_path = os.path.join(tempfile.gettempdir(), "sales_coach_smoke.db")
os.environ["SALES_COACH_DATABASE_URL"] = f"sqlite:///{db_path}"
os.environ["SALES_COACH_DEEPSEEK_API_KEY"] = ""
os.environ["SALES_COACH_DEEPSEEK_GROUP_ID"] = ""
os.environ["SALES_COACH_MIMO_API_KEY"] = ""

import app.seed_kb

# 隔离本机 kb/ 业务资料，保证 smoke 断言不受真实知识库内容影响
app.seed_kb.KB_DIR = Path(tempfile.gettempdir()) / "sales_coach_smoke_kb_empty"

from fastapi.testclient import TestClient

from app.config import settings
from app.db.session import Base, SessionLocal, engine
from app.main import app
from app.models import LLMConfig, TrainingSession, User
from app.seed import main as seed_main
from app.services.auth import hash_password
from app.services.knowledge import find_relevant_knowledge
from app.services.llm import LLMClient, _strip_thinking
from app.services.voice import TTS_MAX_CHARS, VoiceClient, VoiceError, VoiceTimeoutError, is_wav_base64


def login(client: TestClient, username: str) -> dict:
    response = client.post("/api/auth/login", json={"username": username, "password": "123456"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def assert_login_rejected(client: TestClient, username: str):
    response = client.post("/api/auth/login", json={"username": username, "password": "123456"})
    assert response.status_code == 401, response.text


def create_legacy_role_users():
    db = SessionLocal()
    try:
        for username, role in [("supervisor", "supervisor"), ("trainer", "trainer")]:
            if not db.query(User).filter(User.username == username).first():
                db.add(
                    User(
                        username=username,
                        name=username,
                        role=role,
                        password_hash=hash_password("123456"),
                    )
                )
        db.commit()
    finally:
        db.close()


def assert_document_write_denied_for_sales(client: TestClient, headers: dict):
    response = client.post(
        "/api/knowledge/documents",
        headers=headers,
        data={
            "title": "普通用户资料",
            "source_type": "SOP 与话术",
            "source_name": "普通用户资料",
            "version_label": "v1",
            "stage": "通用",
            "scenario": "通用",
            "customer_type": "通用",
        },
        files={"file": ("sales-doc.txt", "普通用户不能上传资料。".encode("utf-8"), "text/plain")},
    )
    assert response.status_code == 403, response.text


def assert_openai_compatible_messages_are_sendable():
    client = LLMClient()
    messages = client._openai_messages([{"sender_type": "BOT", "text": "system prompt"}])
    assert [message["role"] for message in messages] == ["system", "user"]
    assert messages[-1]["content"]
    assert _strip_thinking("<think>hidden</think>\nOK") == "OK"


def upload_document(
    client: TestClient,
    headers: dict,
    *,
    title: str,
    source_type: str,
    version: str,
    body: str,
    stage: str = "通用",
    scenario: str = "通用",
    tags: str = "",
    purpose: str = "",
) -> dict:
    response = client.post(
        "/api/knowledge/documents",
        headers=headers,
        data={
            "title": title,
            "source_type": source_type,
            "source_name": title,
            "tags": tags,
            "purpose": purpose,
            "version_label": version,
            "stage": stage,
            "scenario": scenario,
            "customer_type": "通用",
        },
        files={"file": (f"{title}-{version}.txt", body.encode("utf-8"), "text/plain")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def upload_document_version(client: TestClient, headers: dict, document_id: int, version: str, body: str) -> dict:
    response = client.post(
        f"/api/knowledge/documents/{document_id}/versions",
        headers=headers,
        data={"version_label": version},
        files={"file": (f"manual-{version}.txt", body.encode("utf-8"), "text/plain")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def chunk_types(client: TestClient, headers: dict, document_id: int, page_size: int = 20) -> set[str]:
    response = client.get(f"/api/knowledge/documents/{document_id}/chunks?page=1&page_size={page_size}", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["page_size"] == page_size
    assert body["total"] >= 1
    return {item["chunk_type"] for item in body["items"]}


def assert_document_parsing_flow(client: TestClient, admin_headers: dict):
    product = upload_document(
        client,
        admin_headers,
        title="活性染料固色剂说明书",
        source_type="产品说明书",
        version="v1",
        stage="方案论证",
        scenario="技术交涉",
        tags="固色剂,技术交涉",
        purpose="用于解释产品参数、工艺条件和注意事项。",
        body=(
            "产品参数\n外观：淡黄色液体。固含量：40%。pH：6-8。色牢度提升 1-2 级。\n\n"
            "工艺条件\n建议用量 2-3g/L，温度 40-60℃，处理 20 分钟。\n\n"
            "注意事项\n避免与强阳离子助剂直接混用，储存时保持密封。"
        ),
    )
    assert product["current_version"]["parse_status"] == "parsed"
    assert product["current_version"]["chunk_count"] >= 3
    product_types = chunk_types(client, admin_headers, product["id"])
    assert {"产品参数", "工艺条件", "注意事项"} & product_types

    product = upload_document_version(
        client,
        admin_headers,
        product["id"],
        "v2",
        (
            "产品参数\n外观：浅黄色液体。固含量：42%。湿摩擦色牢度提升更稳定。\n\n"
            "应用场景\n适用于活性染料印染后的固色处理，适合客户做小样对比。\n\n"
            "技术边界\n不建议在未确认浴比和 pH 的情况下承诺绝对稳定。"
        ),
    )
    assert product["current_version"]["version_label"] == "v2"
    active_versions = [item for item in product["versions"] if item["status"] == "active"]
    assert len(active_versions) == 1

    sop = upload_document(
        client,
        admin_headers,
        title="商务谈判 SOP",
        source_type="SOP 与话术",
        version="v1",
        stage="商务谈判",
        scenario="价格异议",
        tags="价格异议,谈判",
        purpose="用于价格异议、禁用话术和评分标准。",
        body=(
            "推荐话术\n先确认客户比较对象，再解释总成本、稳定性和返修风险。\n\n"
            "禁用话术\n不要直接说我们的质量更好，也不要立即降价。\n\n"
            "评分标准\n能否追问客户压价依据、能否给出下一步推进动作。"
        ),
    )
    sop_types = chunk_types(client, admin_headers, sop["id"], page_size=50)
    assert {"推荐话术", "禁用话术", "评分标准"} & sop_types

    db = SessionLocal()
    try:
        session = TrainingSession(
            owner_id=1,
            training_type="客户情景陪练",
            stage="方案论证",
            goal="技术交涉",
            customer_name="锦兴印染",
            customer_type="通用",
            background="客户要求解释湿摩擦色牢度和工艺条件，需要产品说明书依据。",
        )
        items = find_relevant_knowledge(db, session, limit=8)
        sources = {item.source_name for item in items}
        assert "活性染料固色剂说明书 v2" in sources, sources
        assert "活性染料固色剂说明书 v1" not in sources, sources
    finally:
        db.close()

    disabled = client.post(f"/api/knowledge/documents/{product['id']}/toggle", headers=admin_headers)
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["status"] == "disabled"

    db = SessionLocal()
    try:
        session = TrainingSession(
            owner_id=1,
            training_type="客户情景陪练",
            stage="方案论证",
            goal="技术交涉",
            customer_name="锦兴印染",
            customer_type="通用",
            background="客户要求解释湿摩擦色牢度和工艺条件，需要产品说明书依据。",
        )
        items = find_relevant_knowledge(db, session, limit=8)
        sources = {item.source_name for item in items}
        assert "活性染料固色剂说明书 v2" not in sources, sources
    finally:
        db.close()


def start_session(client: TestClient, headers: dict, payload: dict) -> dict:
    payload = {
        "customer_difficulty": "高压",
        "customer_personality": "压价型",
        "customer_concern": "价格",
        "template_id": "price-objection",
        "setup_context": {
            "guide_flow": "scenario_coaching",
            "customer_info": {"product_name": "活性染料固色盐", "product_need": "稳定交付"},
            "scenario_setup": {"scenario": "价格异议", "objection_type": "价格"},
        },
        **payload,
    }
    response = client.post("/api/training/sessions", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["messages"], "AI 客户开场不能为空"
    assert body["messages"][0]["role"] == "customer"
    assert all("id" in message for message in body["messages"])
    assert body["customer_difficulty"] == payload["customer_difficulty"]
    assert body["customer_personality"] == payload["customer_personality"]
    assert body["customer_concern"] == payload["customer_concern"]
    assert body["template_id"] == payload["template_id"]
    assert body["setup_context"]["guide_flow"] == payload["setup_context"]["guide_flow"]
    return body


def finish_session(client: TestClient, headers: dict, session_id: int) -> dict:
    response = client.post(f"/api/training/sessions/{session_id}/finish", headers=headers)
    assert response.status_code == 200, response.text
    report = response.json()
    assert 1 <= report["overall_score"] <= 100
    assert report["summary"]
    assert len(report["scores"]) >= 7
    assert report["citations"]
    return report


def fake_wav_base64() -> str:
    pcm = b"\x00\x01" * 160
    riff = b"RIFF" + (36 + len(pcm)).to_bytes(4, "little") + b"WAVE"
    return base64.b64encode(riff + pcm).decode("ascii")


def assert_voice_flow(client: TestClient, headers: dict):
    settings.mimo_api_key = "sk-mimo-test"

    async def fake_transcribe(self, audio_base64, mime_type):
        assert mime_type == "audio/wav"
        return "你好，我想了解一下价格。"

    async def fake_synthesize(self, text):
        captured_tts.append(text)
        return b"RIFF-fake-wav"

    captured_tts = []
    original_transcribe = VoiceClient.transcribe
    original_synthesize = VoiceClient.synthesize
    VoiceClient.transcribe = fake_transcribe
    VoiceClient.synthesize = fake_synthesize
    try:
        health = client.get("/api/health")
        assert health.json()["voice_configured"] is True

        # 非 wav（magic number 校验）→ 400
        response = client.post(
            "/api/voice/transcribe",
            headers=headers,
            json={"audio_base64": base64.b64encode(b"not-a-wav-file").decode("ascii"), "mime_type": "audio/wav"},
        )
        assert response.status_code == 400, response.text
        # mime 不匹配 → 400
        response = client.post(
            "/api/voice/transcribe",
            headers=headers,
            json={"audio_base64": fake_wav_base64(), "mime_type": "audio/mp3"},
        )
        assert response.status_code == 400, response.text
        # 超大音频 → 413
        response = client.post(
            "/api/voice/transcribe",
            headers=headers,
            json={"audio_base64": "UklGR" + "A" * (8 * 1024 * 1024), "mime_type": "audio/wav"},
        )
        assert response.status_code == 413, response.text
        # 正常识别
        response = client.post(
            "/api/voice/transcribe",
            headers=headers,
            json={"audio_base64": fake_wav_base64(), "mime_type": "audio/wav"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["text"] == "你好，我想了解一下价格。"

        # 正常合成 → audio/wav 字节流，文本先 trim
        response = client.post("/api/voice/speech", headers=headers, json={"text": "  价格方面我们可以再谈。 "})
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("audio/wav")
        assert response.content == b"RIFF-fake-wav"
        assert captured_tts[-1] == "价格方面我们可以再谈。"
        # 超 500 字自动截断，不报错
        response = client.post("/api/voice/speech", headers=headers, json={"text": "长" * 600})
        assert response.status_code == 200, response.text
        assert len(captured_tts[-1]) == TTS_MAX_CHARS
        # 空文本 → 400
        response = client.post("/api/voice/speech", headers=headers, json={"text": "   "})
        assert response.status_code == 400, response.text
    finally:
        VoiceClient.transcribe = original_transcribe
        VoiceClient.synthesize = original_synthesize

    # 超时 → 504；其它上游错误 → 502
    async def timeout_transcribe(self, audio_base64, mime_type):
        raise VoiceTimeoutError("timeout")

    async def broken_synthesize(self, text):
        raise VoiceError("boom")

    VoiceClient.transcribe = timeout_transcribe
    VoiceClient.synthesize = broken_synthesize
    try:
        response = client.post(
            "/api/voice/transcribe",
            headers=headers,
            json={"audio_base64": fake_wav_base64(), "mime_type": "audio/wav"},
        )
        assert response.status_code == 504, response.text
        assert "超时" in response.json()["detail"]
        response = client.post("/api/voice/speech", headers=headers, json={"text": "你好"})
        assert response.status_code == 502, response.text
    finally:
        VoiceClient.transcribe = original_transcribe
        VoiceClient.synthesize = original_synthesize
        settings.mimo_api_key = ""


def run():
    # Save and clear env-based API key so tests run in a clean state
    _saved_api_key = settings.deepseek_api_key
    settings.deepseek_api_key = ""

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    seed_main()
    create_legacy_role_users()
    assert_openai_compatible_messages_are_sendable()

    client = TestClient(app)
    health = client.get("/api/health")
    assert health.status_code == 200, health.text
    health_body = health.json()
    assert health_body["status"] == "ok"
    assert health_body["llm_configured"] is False
    assert health_body["llm_mode"] == "mock"
    assert health_body["voice_configured"] is False
    assert VoiceClient().configured is False
    assert is_wav_base64(base64.b64encode(b"RIFF\x24\x08\x00\x00WAVEfmt ").decode("ascii")) is True
    assert is_wav_base64(base64.b64encode(b"OggS not wav at all").decode("ascii")) is False

    sales_headers = login(client, "sales")
    admin_headers = login(client, "admin")
    assert_login_rejected(client, "supervisor")
    assert_login_rejected(client, "trainer")

    response = client.post(
        "/api/voice/transcribe",
        json={"audio_base64": fake_wav_base64(), "mime_type": "audio/wav"},
    )
    assert response.status_code == 401, response.text
    response = client.post(
        "/api/voice/transcribe",
        headers=sales_headers,
        json={"audio_base64": fake_wav_base64(), "mime_type": "audio/wav"},
    )
    assert response.status_code == 503, response.text

    response = client.get("/api/knowledge")
    assert response.status_code == 401, response.text
    response = client.get("/api/knowledge/documents")
    assert response.status_code == 401, response.text
    response = client.get("/api/knowledge", headers=sales_headers)
    assert response.status_code == 200, response.text
    response = client.get("/api/knowledge/documents", headers=sales_headers)
    assert response.status_code == 200, response.text
    assert_document_write_denied_for_sales(client, sales_headers)

    response = client.get("/api/settings/llm")
    assert response.status_code == 401, response.text
    response = client.get("/api/settings/llm", headers=sales_headers)
    assert response.status_code == 403, response.text
    response = client.get("/api/settings/llm", headers=admin_headers)
    assert response.status_code == 200, response.text
    llm_config = response.json()
    assert llm_config["llm_mode"] == "mock"
    assert llm_config["llm_configured"] is False
    assert llm_config["has_api_key"] is False
    assert "api_key" not in llm_config

    response = client.patch(
        "/api/settings/llm",
        headers=admin_headers,
        json={
            "api_key": "sk-test-secret-1234",
            "base_url": "https://api.deepseek.com",
            "model_name": "DeepSeek V4 Flash",
            "model_id": "deepseek-v4-flash",
        },
    )
    assert response.status_code == 200, response.text
    llm_config = response.json()
    assert llm_config["llm_mode"] == "llm"
    assert llm_config["llm_configured"] is True
    assert llm_config["model_name"] == "DeepSeek V4 Flash"
    assert llm_config["model_id"] == "deepseek-v4-flash"
    assert llm_config["has_api_key"] is True
    assert llm_config["api_key_masked"].endswith("1234")
    assert "sk-test-secret-1234" not in response.text
    db = SessionLocal()
    try:
        stored_config = db.get(LLMConfig, 1)
        assert stored_config
        assert "sk-test-secret-1234" not in stored_config.api_key
        assert stored_config.api_key.startswith("enc:")
    finally:
        db.close()
    health = client.get("/api/health")
    assert health.status_code == 200, health.text
    assert health.json()["llm_mode"] == "llm"

    async def fake_connection_test(self, config):
        assert config.model_id == "deepseek-v4-flash"
        assert config.api_key == "sk-test-secret-1234"
        return {"ok": True, "message": "模型连接成功", "model_id": config.model_id, "latency_ms": 12}

    original_connection_test = getattr(LLMClient, "test_connection", None)
    LLMClient.test_connection = fake_connection_test
    try:
        response = client.post("/api/settings/llm/test", headers=sales_headers)
        assert response.status_code == 403, response.text
        response = client.post("/api/settings/llm/test", headers=admin_headers)
        assert response.status_code == 200, response.text
        test_body = response.json()
        assert test_body["ok"] is True
        assert test_body["model_id"] == "deepseek-v4-flash"
        assert test_body["latency_ms"] == 12
        assert "sk-test-secret-1234" not in response.text
    finally:
        if original_connection_test is None:
            delattr(LLMClient, "test_connection")
        else:
            LLMClient.test_connection = original_connection_test

    response = client.patch(
        "/api/settings/llm",
        headers=admin_headers,
        json={
            "api_key": "sk-test-secret-1234",
            "base_url": "https://example.invalid/v1",
            "model_name": "Other Provider Model",
            "model_id": "other-provider-model",
        },
    )
    assert response.status_code == 400, response.text

    settings.deepseek_api_key = "sk-env-secret-9999"
    response = client.patch(
        "/api/settings/llm",
        headers=admin_headers,
        json={
            "clear_api_key": True,
            "base_url": "https://api.deepseek.com",
            "model_name": "DeepSeek V4 Flash",
            "model_id": "deepseek-v4-flash",
        },
    )
    assert response.status_code == 200, response.text
    # DB key cleared but env var still present → falls back to env → "llm"
    assert response.json()["llm_mode"] == "llm"
    health = client.get("/api/health")
    assert health.status_code == 200, health.text
    assert health.json()["llm_mode"] == "llm"

    # When both DB key and env var are empty → mock mode
    settings.deepseek_api_key = ""
    health = client.get("/api/health")
    assert health.status_code == 200, health.text
    assert health.json()["llm_mode"] == "mock"

    assert_document_parsing_flow(client, admin_headers)

    session = start_session(
        client,
        sales_headers,
        {
            "training_type": "客户情景陪练",
            "stage": "商务谈判",
            "goal": "价格异议",
            "customer_name": "锦兴印染",
            "customer_type": "通用",
            "background": "客户认为报价高，希望先降价，但还没有确认稳定性损耗和返修风险。",
        },
    )
    first_reply = session["messages"][0]["content"]
    assert any(keyword in first_reply for keyword in ["降价", "预算", "成本"]), first_reply
    retry_response = client.post(f"/api/training/sessions/{session['id']}/retry", headers=sales_headers)
    assert retry_response.status_code == 200, retry_response.text
    retry_body = retry_response.json()
    assert retry_body["customer_difficulty"] == "高压"
    assert retry_body["customer_personality"] == "压价型"
    assert retry_body["customer_concern"] == "价格"
    assert retry_body["template_id"] == "price-objection"
    assert retry_body["setup_context"]["guide_flow"] == "scenario_coaching"
    report = finish_session(client, sales_headers, session["id"])
    assert "supervisor_comment" not in report
    assert any(item.get("source") for item in report["citations"])
    comment_response = client.post(
        f"/api/training/reports/{session['id']}/comment",
        headers=admin_headers,
        json={"comment": "不再需要主管点评"},
    )
    assert comment_response.status_code in (404, 405), comment_response.text

    assert_voice_flow(client, sales_headers)

    # Restore env-based API key
    settings.deepseek_api_key = _saved_api_key

    print("smoke ok: documents, chunks, retrieval, report, voice")


if __name__ == "__main__":
    run()
