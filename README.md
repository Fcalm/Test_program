# AI 求职助手

## 项目结构

```
backend/
  main.py                 # FastAPI 入口
  config.py               # 配置（从 .env 读取）
  database.py             # MySQL 异步连接
  models/                 # SQLAlchemy 数据模型
  schemas/                # Pydantic 请求/响应模型
  services/               # 业务逻辑
  routers/                # API 路由
  utils/                  # 工具函数

frontend/demo/            # 前端页面
  login.html              # 登录页
  register.html           # 注册页
  survey.html             # 问卷页
  index.html              # 首页
  ai-resume-assistant.html # AI 简历助手
```

## 启动方式

```bash
# 1. 配置 .env（MySQL 连接信息、JWT 密钥等）
# 2. 创建数据库
#    CREATE DATABASE resume_agent CHARACTER SET utf8mb4;
# 3. 安装依赖
pip install -r requirements.txt
# 4. 启动后端
uvicorn backend.main:app --reload
# 5. 打开前端页面
start frontend/demo/login.html
```

## API 文档

启动后访问 http://localhost:8000/docs

---

## ⚠️ 临时测试需求（agent 开发后删除）

### 001 JD 解析脚本测试入口

JD 解析脚本（`backend/services/jd_parser.py`）是 agent 工具，由 agent 决定是否触发。当前 agent 未开发，临时通过前端聊天框触发测试：

- **测试方式**：在简历助手聊天框中发送包含"岗位"、"职责"、"要求"等关键词的 JD 文本（>100 字符），前端自动调用 `POST /tools/parse-jd` 解析并展示结果。
- **临时文件**：`backend/routers/tools.py`（工具测试路由）
- **删除条件**：agent 开发完成后，删除以下内容：
  1. `backend/routers/tools.py` 文件
  2. `backend/main.py` 中 `app.include_router(tools_router)` 那行
  3. `ai-resume-assistant.html` 中 `isJDText()`、`formatJDResult()` 函数及 `sendMessage()` 中的 JD 检测逻辑

### 002 简历解析脚本测试入口

简历解析脚本（`backend/services/resume_parser.py`）是 agent 工具，由 agent 决定是否触发。当前 agent 未开发，临时通过前端"上传简历"按钮触发测试：

- **测试方式**：在简历助手页面点击"上传简历"按钮，选择 PDF/DOCX 文件，前端调用 `POST /tools/upload-resume` 解析并更新简历数据。
- **临时文件**：`backend/routers/tools.py` 中的 `/upload-resume` 路由
- **删除条件**：agent 开发完成后，删除以下内容：
  1. `backend/routers/tools.py` 中 `upload_resume` 函数
  2. `ai-resume-assistant.html` 中 `uploadResume()` 函数的文件上传逻辑（恢复为原始 `alert` 提示）
