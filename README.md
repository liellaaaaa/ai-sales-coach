# AI 销售陪练 MVP 工程

这是从静态原型进入 MVP 的工程骨架，目标是先跑通真实训练闭环：

业务员登录 → 创建训练 → AI 客户对话 → 完成复盘 → 保存历史 → 知识库提供依据。

## 当前包含

- 前端：React + Vite
- 后端：FastAPI
- 数据库：PostgreSQL
- 模型：MiniMax 适配层
- 降级：没有 MiniMax 密钥时，后端会返回模拟客户回复和模拟复盘，方便先跑流程

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

## MiniMax 配置

在 `backend/.env` 中补充：

```env
SALES_COACH_MINIMAX_API_KEY=你的密钥
SALES_COACH_MINIMAX_GROUP_ID=你的 GroupId
SALES_COACH_MINIMAX_MODEL=abab6.5s-chat
```

如果不填写，系统仍可用模拟回复跑通流程。

## MVP 边界

首版不做：

- CRM 对接
- 绩效考核
- 复杂组织树
- 团队排行榜
- 完整知识审核流
- 复杂后台运营系统

首版重点：

- 训练真实可用
- 知识库能作为依据
- 管理员可导入和管理知识资料，普通用户可查看资料列表
- 复盘能保存
- 历史训练能一键再次训练
- 后续可继续扩展
