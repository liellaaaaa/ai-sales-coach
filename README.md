# AI 销售陪练 MVP 工程

这是从静态原型进入 MVP 的工程骨架，目标是先跑通真实训练闭环：

业务员登录 → 创建训练 → AI 多角色客户对话 → 实时教练提示 → 完成复盘 → 保存历史 → 知识库 / 产品卡提供依据。

## 当前包含

- 前端：React + Vite（模块化 `pages/` + `voice.jsx` + `audio.js`）
- 后端：FastAPI
- 数据库：PostgreSQL
- 模型：DeepSeek V4 Flash（OpenAI 兼容接口）
- 语音：MiMo ASR / TTS（按角色分音色）
- 降级：没有 API Key 时，后端会返回模拟客户回复和模拟复盘，方便先跑流程

## 核心能力

- **训练闭环**：客户情景陪练 / 商机推进教练两条向导
- **产品卡 grounded**：11 张产品-工艺-故障卡注入 LLM，客户按型号/参数/工艺追问
- **七维行业评分**：工艺探询 / 产品选型 / 技术边界 / 异议处理 / 故障归因 / 价值合规 / 推进动作
- **多角色客户**：采购（buyer）/ 技术主管（tech）/ 厂长（boss），分音色 TTS
- **实时教练**：live-tip 旁路短提示 + 对话页教练条
- **准全双工交互**：播放中打断、按住说话、语音录入与自动朗读

## 首版角色

演示账号通过 seed 初始化：

- `sales` / `123456`：业务员
- `admin` / `123456`：系统管理员

## 本地运行

1. 启动 PostgreSQL

```bash
docker compose up -d
```

2. 后端安装依赖并初始化数据

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy ..\.env.example .env
python -m app.seed
uvicorn app.main:app --reload
```

3. 前端启动

```bash
cd frontend
npm install
npm run dev
```

默认前端地址：`http://127.0.0.1:5173`

也可使用一键脚本（含 HTTPS 开发适配）：

```powershell
.\start-mvp.ps1
```

## DeepSeek 配置

在 `backend/.env` 中补充：

```env
SALES_COACH_DEEPSEEK_API_KEY=你的密钥
SALES_COACH_DEEPSEEK_BASE_URL=https://api.deepseek.com
SALES_COACH_DEEPSEEK_MODEL=deepseek-v4-flash
```

如果不填写，系统仍可用模拟回复跑通流程。

## 语音配置（可选）

配置 MiMo 语音服务后，训练对话支持语音录入、自动朗读与多角色分音色；未配置时前端自动隐藏语音入口。详见 `docs/superpowers/specs/2026-08-10-voice-asr-tts-design.md`。

## 验证

```powershell
# 后端 smoke（含 documents / chunks / retrieval / report / voice / live-tip）
cd backend
.\.venv\Scripts\python.exe -m app.smoke_test

# 前端构建
cd frontend
npm run build
```

## MVP 边界

首版不做：

- CRM 对接
- 绩效考核
- 复杂组织树
- 团队排行榜
- 完整知识审核流
- 复杂后台运营系统

首版重点：

- 训练真实可用，贴行业产品与工艺
- 知识库 + 产品卡能作为依据
- 管理员可导入和管理知识资料，普通用户可查看资料列表
- 复盘能保存，评分像行业教练
- 历史训练能一键再次训练
- 后续可继续扩展

## 目录速览

```
backend/app/
  main.py models.py schemas.py
  routers/   auth knowledge training voice dashboard settings
  services/  llm knowledge document_parser product_cards voice llm_config auth
frontend/src/
  App.jsx api.js audio.js voice.jsx
  pages/  StartTraining Chat Report Knowledge Dashboard History ...
  constants/training.js
kb/          业务语料（产品卡来源）
docs/        交接 / 接口 / 后续清单 / ASR-TTS 设计
```
