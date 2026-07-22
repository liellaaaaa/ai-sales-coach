# AGENTS.md

## 项目性质

这是 AI 销售陪练 MVP 工程，包含 React/Vite 前端、FastAPI 后端和 PostgreSQL 本地开发环境。

## GitHub 入库边界

- 不上传真实 `.env`、API Key、Token、Cookie、数据库文件、上传文件、客户资料或业务 Excel。
- `.env.example` 可以上传，但只能放占位值。
- `backend/.venv/`、`frontend/node_modules/`、`frontend/dist/`、`__pycache__/` 不进仓库。

## 常用命令

后端：

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.smoke_test
```

前端：

```powershell
cd frontend
npm run build
```

整体验证：

```powershell
.\start-mvp.ps1
```

## 工作准则

- 修改前先确认任务目标和影响范围。
- 只做必要改动，不顺手重构无关文件。
- 提交前检查 `git status`，确认没有敏感文件或生成物进入暂存区。
- push 前优先运行后端 smoke test 和前端 build；如无法运行，需要说明原因。
