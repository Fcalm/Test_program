# 前端约定

## 技术栈

- **生产前端**：`frontend/src/` — React + CSS Modules
- **旧版 demo**：`frontend/demo-禁止修改/` — 纯静态 HTML，**禁止修改**

## 生产前端结构

```
frontend/src/
  pages/       → 页面组件（Resume, InterviewList, InterviewChat 等）
  components/  → 通用组件（ChatInput, ChatMessage, Toast 等）
  lib/         → 工具函数（api.js）
  hooks/       → 自定义 hooks（useSSE）
```

## 样式方案

- 使用 CSS Modules：`import styles from './Xxx.module.css'`
- 类名通过 `styles.xxx` 访问
- 全局 CSS 变量定义在 `index.css` 的 `:root` 中

## API 调用方式

```javascript
import { apiJson, apiFetch, apiDelete } from '../lib/api'

// GET 请求
const data = await apiJson('/resume')

// POST/PUT 请求
const data = await apiFetch('/resume', { method: 'PUT', body: JSON.stringify(payload) })

// DELETE 请求
await apiDelete('/resume/history/123')
```

- Token 自动从 localStorage 读取，通过 `api.js` 统一注入 Header
- 401 响应自动跳转登录页

## demo 目录规则

`frontend/demo-禁止修改/` 为旧版纯静态 HTML 页面，**任何情况下禁止修改**。
