/**
 * 公共工具函数 — 所有页面共享
 * 文件：frontend/demo/utils.js
 */

const API_BASE = 'http://localhost:8000'; // 开发环境，部署时需替换为 HTTPS 地址

/** HTML 实体转义，防止 XSS */
function escapeHtml(text) {
    if (text == null) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

/** 显示 toast 提示 */
function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.textContent = message;
    toast.className = `toast ${type} show`;
    setTimeout(() => toast.classList.remove('show'), 3000);
}

/** 检查登录状态，未登录跳转 login.html */
function checkAuth() {
    const token = localStorage.getItem('token');
    if (!token) {
        window.location.href = 'login.html';
        return null;
    }
    return token;
}

/** 带认证的 fetch 封装，自动处理 401 */
async function apiFetch(path, options = {}) {
    const token = localStorage.getItem('token');
    const headers = { 'Content-Type': 'application/json', ...options.headers };
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

    if (res.status === 401) {
        localStorage.removeItem('token');
        window.location.href = 'login.html';
        throw new Error('未登录或登录已过期');
    }

    return res;
}

/** AI 头像 SVG 常量 */
const AI_AVATAR_SVG = `<svg viewBox="0 0 24 24"><path d="M12 14c1.66 0 2.99-1.34 2.99-3L15 5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z"/></svg>`;
