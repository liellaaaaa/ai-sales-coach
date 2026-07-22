# Training Templates And Customer Parameters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make starting a training session faster and more realistic by adding scenario templates plus customer difficulty, personality, and concern parameters.

**Architecture:** Keep the first iteration inside the existing FastAPI + React/Vite structure. Persist customer parameters on `training_sessions`, expose them through existing training APIs, and make both mock replies and real LLM prompts consume the same fields. Keep `frontend/src/App.jsx` as the primary UI file for this phase, but isolate new constants and helpers inside clear named sections to avoid broad refactors.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, React 18, Vite, existing backend smoke test.

---

## Scope And Product Decisions

This plan implements phase 1 only: training templates and customer parameters.

Included:
- 5 preset training templates.
- Customer difficulty: `标准`, `刁钻`, `高压`.
- Customer personality: `谨慎型`, `压价型`, `专业型`, `敷衍型`.
- Customer concern: `价格`, `交期`, `品质`, `售后`.
- Template cards on the start-training page.
- Persisted backend fields so history/retry keeps the selected profile.
- Mock and LLM customer replies that reflect the selected profile.

Not included in this phase:
- Training-in-progress UX changes such as changing customer reply.
- Report redesign.
- Knowledge base health dashboard.
- Admin user management.

Compatibility rule:
- Old sessions without new fields must continue to load and retry with default values.

---

## File Map

- Modify `backend/app/models.py`
  - Add `customer_difficulty`, `customer_personality`, `customer_concern`, and `template_id` columns to `TrainingSession`.

- Modify `backend/app/schemas.py`
  - Add the same fields to `TrainingStartIn` with defaults.
  - Add the same fields to `TrainingSessionOut`.

- Modify `backend/app/db/migrations.py`
  - Add runtime schema backfill for old local databases.

- Modify `backend/app/routers/training.py`
  - Preserve new fields when retrying a session.

- Modify `backend/app/services/llm.py`
  - Add customer profile context to real LLM prompt.
  - Make mock customer replies vary by difficulty/personality/concern.

- Modify `backend/app/smoke_test.py`
  - Add regression coverage for template/profile fields, retry persistence, and mock reply influence.

- Modify `frontend/src/App.jsx`
  - Add template constants and customer profile options.
  - Render template cards in `StartTraining`.
  - Add customer difficulty/personality/concern controls.
  - Include new fields in `buildTrainingPayload` and `sessionPayloadFromSession`.

- Modify `frontend/src/styles.css`
  - Style template cards and compact customer-profile controls.

---

### Task 1: Backend Session Fields And Compatibility

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/db/migrations.py`
- Test: `backend/app/smoke_test.py`

- [ ] **Step 1: Write the failing smoke test**

Add assertions to `start_session` in `backend/app/smoke_test.py` so it sends the new fields and expects them back.

```python
def start_session(client: TestClient, headers: dict, payload: dict) -> dict:
    payload = {
        "customer_difficulty": "高压",
        "customer_personality": "压价型",
        "customer_concern": "价格",
        "template_id": "price-objection",
        **payload,
    }
    response = client.post("/api/training/sessions", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"]
    assert body["messages"][0]["role"] == "customer"
    assert body["customer_difficulty"] == payload["customer_difficulty"]
    assert body["customer_personality"] == payload["customer_personality"]
    assert body["customer_concern"] == payload["customer_concern"]
    assert body["template_id"] == payload["template_id"]
    return body
```

Also add retry assertions after the existing session is created:

```python
retry_response = client.post(f"/api/training/sessions/{session['id']}/retry", headers=sales_headers)
assert retry_response.status_code == 200, retry_response.text
retry_body = retry_response.json()
assert retry_body["customer_difficulty"] == "高压"
assert retry_body["customer_personality"] == "压价型"
assert retry_body["customer_concern"] == "价格"
assert retry_body["template_id"] == "price-objection"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.smoke_test
```

Expected: FAIL with missing response fields such as `KeyError: 'customer_difficulty'` or a Pydantic response validation error.

- [ ] **Step 3: Add model fields**

In `backend/app/models.py`, add these columns to `TrainingSession` after `customer_type`:

```python
    customer_difficulty: Mapped[str] = mapped_column(String(40), default="标准")
    customer_personality: Mapped[str] = mapped_column(String(40), default="谨慎型")
    customer_concern: Mapped[str] = mapped_column(String(40), default="价格")
    template_id: Mapped[str] = mapped_column(String(80), default="")
```

- [ ] **Step 4: Add schema fields**

In `backend/app/schemas.py`, add these fields to both `TrainingStartIn` and `TrainingSessionOut`:

```python
    customer_difficulty: str = "标准"
    customer_personality: str = "谨慎型"
    customer_concern: str = "价格"
    template_id: str = ""
```

- [ ] **Step 5: Backfill old local databases**

In `backend/app/db/migrations.py`, add training-session column backfill.

```python
    session_columns = {column["name"] for column in inspector.get_columns("training_sessions")} if "training_sessions" in tables else set()

    if session_columns:
        for name, column_type in {
            "customer_difficulty": "VARCHAR(40) DEFAULT '标准'",
            "customer_personality": "VARCHAR(40) DEFAULT '谨慎型'",
            "customer_concern": "VARCHAR(40) DEFAULT '价格'",
            "template_id": "VARCHAR(80) DEFAULT ''",
        }.items():
            if name not in session_columns:
                statements.append(f"ALTER TABLE training_sessions ADD COLUMN {name} {column_type}")
```

Place it before the `if not statements:` block.

- [ ] **Step 6: Preserve profile on retry**

In `backend/app/routers/training.py`, add these fields when creating the retry session:

```python
        customer_difficulty=source.customer_difficulty,
        customer_personality=source.customer_personality,
        customer_concern=source.customer_concern,
        template_id=source.template_id,
```

- [ ] **Step 7: Run test to verify backend fields pass**

Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.smoke_test
```

Expected: the previous field-related failure is gone. If later tasks are not implemented yet, failures should point only to prompt/mock behavior added in Task 2.

- [ ] **Step 8: Commit backend persistence**

```powershell
git add backend/app/models.py backend/app/schemas.py backend/app/db/migrations.py backend/app/routers/training.py backend/app/smoke_test.py
git commit -m "add training customer profile fields"
```

---

### Task 2: Customer Profile In Mock And LLM Prompts

**Files:**
- Modify: `backend/app/services/llm.py`
- Test: `backend/app/smoke_test.py`

- [ ] **Step 1: Write failing mock behavior test**

In `backend/app/smoke_test.py`, after creating a session with `customer_difficulty="高压"` and `customer_personality="压价型"`, assert the first customer reply reflects the tougher price-pressure profile.

```python
    first_reply = session["messages"][0]["content"]
    assert any(keyword in first_reply for keyword in ["价格", "降价", "预算", "成本"]), first_reply
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.smoke_test
```

Expected: FAIL because current mock replies do not reliably mention price-pressure context.

- [ ] **Step 3: Add profile summary helper**

In `backend/app/services/llm.py`, add a helper near `_knowledge_text`:

```python
def _customer_profile_text(session: TrainingSession) -> str:
    difficulty = getattr(session, "customer_difficulty", "") or "标准"
    personality = getattr(session, "customer_personality", "") or "谨慎型"
    concern = getattr(session, "customer_concern", "") or "价格"
    return f"客户难度：{difficulty}；客户性格：{personality}；核心关注：{concern}"
```

- [ ] **Step 4: Add profile to real LLM customer prompt**

In `MiniMaxClient.customer_reply`, add the profile line after customer info:

```python
            f"客户：{session.customer_name} / {session.customer_type}\n"
            f"{_customer_profile_text(session)}\n"
            f"背景：{session.background}\n"
```

Also strengthen the instruction:

```python
            "客户回复必须体现客户难度、性格和核心关注点，不要过早让步。\n"
```

- [ ] **Step 5: Make mock replies profile-aware**

Replace `_mock_customer_reply` with this shape, keeping return length concise:

```python
    def _mock_customer_reply(self, session: TrainingSession, messages: list[TrainingMessage]) -> str:
        sales_turns = [m for m in messages if m.role == "sales"]
        concern = getattr(session, "customer_concern", "") or "价格"
        difficulty = getattr(session, "customer_difficulty", "") or "标准"
        personality = getattr(session, "customer_personality", "") or "谨慎型"

        if concern == "价格":
            opening = "价格和预算是我现在最关注的点"
        elif concern == "交期":
            opening = "交期能不能保证是我现在最担心的点"
        elif concern == "品质":
            opening = "品质稳定性和返工风险我需要先确认"
        else:
            opening = "售后响应和后续服务我需要先看清楚"

        if difficulty == "高压":
            pressure = "如果没有更明确的让利或保障，我很难继续推进。"
        elif difficulty == "刁钻":
            pressure = "你现在的说法还不够具体，我需要看到依据。"
        else:
            pressure = "你可以先把对我们实际有利的部分讲清楚。"

        if personality == "敷衍型":
            pressure = "我时间不多，你直接说重点。"
        elif personality == "专业型":
            pressure = "最好能给到数据、案例或测试条件。"

        if len(sales_turns) <= 1:
            return f"{opening}。{pressure}"
        if len(sales_turns) == 2:
            return f"听起来有点道理，但围绕{concern}我还没被说服。下一步你准备怎么安排？"
        return f"如果要继续推进，请把{concern}相关的条件、时间和负责人说清楚，否则我这边很难排优先级。"
```

- [ ] **Step 6: Run backend smoke test**

Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.smoke_test
```

Expected: PASS.

- [ ] **Step 7: Commit prompt/mock behavior**

```powershell
git add backend/app/services/llm.py backend/app/smoke_test.py
git commit -m "make customer replies use profile settings"
```

---

### Task 3: Frontend Templates And Customer Controls

**Files:**
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend` build

- [ ] **Step 1: Add template and profile constants**

In `frontend/src/App.jsx`, near the existing training constants, add:

```jsx
const customerDifficultyOptions = ["标准", "刁钻", "高压"];
const customerPersonalityOptions = ["谨慎型", "压价型", "专业型", "敷衍型"];
const customerConcernOptions = ["价格", "交期", "品质", "售后"];

const trainingTemplates = [
  {
    id: "price-objection",
    title: "价格异议",
    subtitle: "客户认为报价偏高",
    training_type: "客户情景陪练",
    stage: "商务谈判",
    goal: "价格异议",
    customer_type: "新客户，价格敏感",
    product_need: "需要稳定交付，但希望先压低采购成本",
    background: "客户正在比较多家供应商，认为当前报价偏高，希望先降价再继续谈。",
    customer_difficulty: "高压",
    customer_personality: "压价型",
    customer_concern: "价格",
  },
  {
    id: "delivery-risk",
    title: "交期确认",
    subtitle: "客户担心交付延误",
    training_type: "客户情景陪练",
    stage: "方案论证",
    goal: "交期保障",
    customer_type: "渠道客户，关注交期",
    product_need: "需要按期交付，避免影响下游排产",
    background: "客户担心旺季交付不稳定，要求说明排产、备货和异常处理方案。",
    customer_difficulty: "刁钻",
    customer_personality: "谨慎型",
    customer_concern: "交期",
  },
  {
    id: "quality-proof",
    title: "品质质疑",
    subtitle: "客户要求稳定性依据",
    training_type: "客户情景陪练",
    stage: "方案论证",
    goal: "技术质疑",
    customer_type: "技术型客户，关注工艺",
    product_need: "需要确认稳定性、测试条件和返工风险",
    background: "客户技术负责人要求看到测试条件、稳定性数据和异常处理边界。",
    customer_difficulty: "刁钻",
    customer_personality: "专业型",
    customer_concern: "品质",
  },
  {
    id: "stalled-opportunity",
    title: "商机停滞",
    subtitle: "资料发出后客户没有推进",
    training_type: OPPORTUNITY_MODE,
    stage: "确认商机",
    goal: "商机停滞",
    customer_type: "新客户，内部决策不清晰",
    product_need: "需要确认关键人和下一步测试条件",
    background: "客户收资料后没有明确反馈，需要重新推动关键人参与和下一步动作。",
    last_contact: "客户说先内部看看资料，之后一直没有明确反馈。",
    decision_blocker: "关键人未参与",
    next_milestone: "约到关键人会议",
    stakeholder: "采购已沟通，技术负责人还未参与",
    customer_difficulty: "标准",
    customer_personality: "敷衍型",
    customer_concern: "售后",
  },
  {
    id: "payment-followup",
    title: "回款推进",
    subtitle: "客户拖延付款节点",
    training_type: "客户情景陪练",
    stage: "回款",
    goal: "回款交涉",
    customer_type: "老客户，流程较慢",
    product_need: "需要确认付款流程、责任人和预计时间",
    background: "客户已经确认订单和交付，但付款流程迟迟没有明确时间。",
    customer_difficulty: "标准",
    customer_personality: "谨慎型",
    customer_concern: "售后",
  },
];
```

- [ ] **Step 2: Extend `defaultForm`**

Add these defaults wherever `defaultForm` is defined:

```jsx
  customer_difficulty: "标准",
  customer_personality: "谨慎型",
  customer_concern: "价格",
  template_id: "",
```

- [ ] **Step 3: Add template selection helper**

Inside `StartTraining`, add:

```jsx
  function applyTemplate(template) {
    const nextStage = opportunityStages.find((stage) => stage.name === template.stage) || opportunityStages[0];
    const nextGoals = stageTrainingGoals[nextStage.name] || trainingGoals;
    const nextGoal = nextGoals.some((goal) => goal.name === template.goal) ? template.goal : nextGoals[0].name;
    setForm({
      ...form,
      ...template,
      stage: nextStage.name,
      goal: nextGoal,
      template_id: template.id,
    });
    setSetupSaved(false);
    onError("");
  }
```

- [ ] **Step 4: Render template cards before customer info**

Inside `!setupSaved && <div className="setup-block">`, before the existing customer info block, render:

```jsx
            <div className="template-block">
              <div className="section-title">
                <h4>常用训练模板</h4>
                <span className="hint">点选模板后可继续微调客户信息和训练目标。</span>
              </div>
              <div className="template-grid">
                {trainingTemplates.map((template) => (
                  <button
                    key={template.id}
                    type="button"
                    className={`template-card ${form.template_id === template.id ? "active" : ""}`}
                    onClick={() => applyTemplate(template)}
                  >
                    <b>{template.title}</b>
                    <span>{template.subtitle}</span>
                    <small>{template.customer_personality} · {template.customer_concern}</small>
                  </button>
                ))}
              </div>
            </div>
```

- [ ] **Step 5: Add customer profile controls**

After the existing basic customer fields, add:

```jsx
              <div className="profile-tuning">
                <label>客户难度<select value={form.customer_difficulty} onChange={(e) => updateSetup({ customer_difficulty: e.target.value })}>{customerDifficultyOptions.map((item) => <option key={item}>{item}</option>)}</select></label>
                <label>客户性格<select value={form.customer_personality} onChange={(e) => updateSetup({ customer_personality: e.target.value })}>{customerPersonalityOptions.map((item) => <option key={item}>{item}</option>)}</select></label>
                <label>核心关注<select value={form.customer_concern} onChange={(e) => updateSetup({ customer_concern: e.target.value })}>{customerConcernOptions.map((item) => <option key={item}>{item}</option>)}</select></label>
              </div>
```

- [ ] **Step 6: Include fields in request payload**

In `buildTrainingPayload`, add the fields:

```jsx
    customer_difficulty: form.customer_difficulty,
    customer_personality: form.customer_personality,
    customer_concern: form.customer_concern,
    template_id: form.template_id,
```

- [ ] **Step 7: Preserve fields in retry payload**

In `sessionPayloadFromSession`, add:

```jsx
    customer_difficulty: item.customer_difficulty || "标准",
    customer_personality: item.customer_personality || "谨慎型",
    customer_concern: item.customer_concern || "价格",
    template_id: item.template_id || "",
```

- [ ] **Step 8: Add styles**

In `frontend/src/styles.css`, add:

```css
.template-block {
  display: grid;
  gap: 14px;
}

.template-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
}

.template-card {
  min-height: 108px;
  border: 1px solid rgba(86, 108, 135, 0.18);
  background: #fff;
  border-radius: 8px;
  padding: 14px;
  text-align: left;
  display: grid;
  gap: 6px;
  cursor: pointer;
}

.template-card:hover,
.template-card.active {
  border-color: #2474ff;
  box-shadow: 0 10px 24px rgba(36, 116, 255, 0.12);
}

.template-card b {
  font-size: 15px;
}

.template-card span,
.template-card small {
  color: #526078;
  line-height: 1.4;
}

.profile-tuning {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

@media (max-width: 760px) {
  .profile-tuning {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 9: Run frontend build**

Run:

```powershell
cd frontend
npm.cmd run build
```

Expected: PASS.

- [ ] **Step 10: Commit frontend template UI**

```powershell
git add frontend/src/App.jsx frontend/src/styles.css
git commit -m "add training templates and customer controls"
```

---

### Task 4: Browser QA And Full Verification

**Files:**
- No required code files.
- Optional fixes in `frontend/src/App.jsx` or `frontend/src/styles.css` only if QA reveals UI issues.

- [ ] **Step 1: Run backend smoke test**

Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.smoke_test
```

Expected: PASS.

- [ ] **Step 2: Run frontend build**

Run:

```powershell
cd frontend
npm.cmd run build
```

Expected: PASS.

- [ ] **Step 3: Run diff check**

Run:

```powershell
git diff --check
```

Expected: exit 0. Windows LF/CRLF warnings are acceptable; whitespace errors are not.

- [ ] **Step 4: Browser verify start-training UX**

Use the in-app browser at `http://127.0.0.1:5173/`.

Manual path:
1. Login as `sales / 123456`.
2. Open `开始训练`.
3. Click template `价格异议`.
4. Confirm customer fields and profile controls are populated.
5. Change `客户难度` to `高压`.
6. Save setup.
7. Create training.
8. Confirm first customer reply references price/budget/cost pressure.

Expected: no console errors, no layout overflow on desktop viewport.

- [ ] **Step 5: Browser verify retry compatibility**

Manual path:
1. Open `历史记录`.
2. Retry the newly created training.
3. Confirm the new session starts normally.

Expected: no missing-field crashes; customer profile fields are preserved through retry.

- [ ] **Step 6: Final status and commit if QA fixes were needed**

If any QA fixes were made:

```powershell
git add frontend/src/App.jsx frontend/src/styles.css
git commit -m "polish training template setup"
```

If no QA fixes were made, do not create an empty commit.

---

## Test Matrix

Backend:
- `backend/.venv/Scripts/python.exe -m app.smoke_test`

Frontend:
- `frontend`: `npm.cmd run build`

Git:
- `git diff --check`
- `git status -sb`

Browser:
- Sales user can pick a template and start training.
- Template fields populate correctly.
- Customer profile controls are visible and editable.
- First mock customer reply reflects selected concern/difficulty.
- Retry preserves customer profile fields.

---

## Rollout Notes

- This plan changes the training session table. Existing local databases should be updated by `ensure_runtime_schema()` on app startup.
- Existing training sessions get default values through database defaults and schema fallbacks.
- The frontend should keep old sessions safe by using `item.customer_difficulty || "标准"` style fallbacks.
- This phase does not require a real LLM key. Mock mode must remain useful.
- If real LLM is configured, prompt changes should improve customer simulation without changing API shape.

---

## Self-Review

- Spec coverage: The plan covers training templates, customer difficulty, personality, concern, persistence, retry, mock/LLM behavior, UI, styles, and verification.
- Placeholder scan: No `TBD` or open-ended implementation steps are left.
- Type consistency: Backend and frontend use the same field names: `customer_difficulty`, `customer_personality`, `customer_concern`, `template_id`.
- Scope check: This plan is limited to phase 1 and does not include report redesign, training chat enhancements, admin dashboard, or knowledge-base health.
