/**
 * AI 面试对话页 — JavaScript 逻辑
 * 文件：frontend/demo/ai-interview-chat.js
 */

const API_BASE = 'http://localhost:8000';

const AI_AVATAR_SVG = `<svg viewBox="0 0 24 24"><path d="M12 14c1.66 0 2.99-1.34 2.99-3L15 5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z"/></svg>`;

// ===== 全局状态 =====
const state = {
    sessionId: null,       // 面试 session ID
    round: 1,              // 当前轮次 1=技术面 2=Leader面
    paused: false,         // 是否暂停
    tipsEnabled: true,     // 是否显示提示
    questionCount: 0,      // 已答题数
    timerSeconds: 0,       // 计时器秒数
    timerInterval: null,   // 计时器 interval
    isStreaming: false,    // 是否正在流式接收
    chatHistory: [],       // 对话历史 [{role, content}]
    roundSwitched: false,  // 是否已切换轮次
    interviewEnded: false, // 面试是否结束
};

// ===== 页面初始化 =====
document.addEventListener('DOMContentLoaded', () => {
    checkAuth();
    initFromURL();
    startTimer();
});

/** 检查登录状态 */
function checkAuth() {
    const token = localStorage.getItem('token');
    if (!token) {
        window.location.href = 'login.html';
    }
}

/** 从 URL 解析 session_id 和 JD 信息 */
function initFromURL() {
    const params = new URLSearchParams(window.location.search);
    state.sessionId = params.get('session_id');

    const title = params.get('title');
    const jdCompany = params.get('company');
    const jdPosition = params.get('position');

    if (title) {
        document.getElementById('interviewTitle').textContent = title;
    } else if (jdCompany && jdPosition) {
        document.getElementById('interviewTitle').textContent = `${jdCompany} - ${jdPosition}`;
    }

    document.getElementById('interviewSubtitle').textContent = '第1轮 · 技术面';

    if (!state.sessionId) {
        // 无 session_id，显示开场提示
        addSystemMessage('未检测到面试会话。请从面试主页开始新的面试。');
        disableInput();
    } else {
        // 有 session_id，发送开场请求
        addSystemMessage('面试即将开始，AI 面试官正在准备...');
        startInterview();
    }
}

// ===== 计时器 =====
function startTimer() {
    state.timerInterval = setInterval(() => {
        if (!state.paused && !state.interviewEnded) {
            state.timerSeconds++;
            updateTimerDisplay();
        }
    }, 1000);
}

function updateTimerDisplay() {
    const min = Math.floor(state.timerSeconds / 60);
    const sec = state.timerSeconds % 60;
    document.getElementById('timer').textContent =
        `${String(min).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
}

// ===== 暂停 / 继续 =====
function togglePause() {
    state.paused = !state.paused;
    const btn = document.getElementById('pauseBtn');
    const overlay = document.getElementById('pauseOverlay');
    const statusBadge = document.getElementById('statusBadge');
    const statusDot = document.getElementById('statusDot');
    const statusText = document.getElementById('statusText');
    const inputWrapper = document.getElementById('inputWrapper');

    if (state.paused) {
        btn.classList.add('paused');
        btn.innerHTML = `
            <svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
            <span>继续</span>
        `;
        overlay.classList.add('visible');
        statusBadge.className = 'status-badge paused-status';
        statusDot.className = 'status-dot yellow';
        statusText.textContent = '已暂停';
        inputWrapper.classList.add('disabled');
    } else {
        btn.classList.remove('paused');
        btn.innerHTML = `
            <svg viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
            <span>暂停</span>
        `;
        overlay.classList.remove('visible');
        statusBadge.className = 'status-badge active-status';
        statusDot.className = 'status-dot green';
        statusText.textContent = '进行中';
        inputWrapper.classList.remove('disabled');
    }
}

// ===== 提示开关 =====
function toggleTips() {
    state.tipsEnabled = !state.tipsEnabled;
    const track = document.getElementById('tipsTrack');

    if (state.tipsEnabled) {
        track.classList.add('active');
    } else {
        track.classList.remove('active');
    }

    // 同步所有已有消息的 tips 显示
    document.querySelectorAll('.message-tips').forEach(el => {
        if (state.tipsEnabled) {
            el.classList.remove('hidden');
        } else {
            el.classList.add('hidden');
        }
    });
}

// ===== 输入处理 =====
function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

function autoResizeTextarea() {
    const textarea = document.getElementById('messageInput');
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 100) + 'px';
}

function disableInput() {
    document.getElementById('inputWrapper').classList.add('disabled');
    document.getElementById('messageInput').disabled = true;
    document.getElementById('sendBtn').disabled = true;
}

function enableInput() {
    document.getElementById('inputWrapper').classList.remove('disabled');
    document.getElementById('messageInput').disabled = false;
    document.getElementById('sendBtn').disabled = false;
}

function clearInput() {
    const textarea = document.getElementById('messageInput');
    textarea.value = '';
    textarea.style.height = 'auto';
}

// ===== 更新题数显示 =====
function updateQuestionCount() {
    document.getElementById('questionCount').textContent = `已答 ${state.questionCount} 题`;
}

// ===== 更新轮次显示 =====
function updateRoundDisplay() {
    const badge = document.getElementById('roundBadge');
    const subtitle = document.getElementById('interviewSubtitle');

    if (state.round === 1) {
        badge.textContent = '第1轮 · 技术面';
        subtitle.textContent = '第1轮 · 技术面';
    } else {
        badge.textContent = '第2轮 · Leader面';
        subtitle.textContent = '第2轮 · Leader面';
    }
}

// ===== Toast 提示 =====
function showToast(message, isError = false) {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = 'toast show' + (isError ? ' error' : '');
    setTimeout(() => { toast.className = 'toast'; }, 3000);
}

// ===== 帮助弹窗 =====
function showHelp() {
    document.getElementById('helpModal').classList.add('active');
}

function closeHelp() {
    document.getElementById('helpModal').classList.remove('active');
}

document.getElementById('helpModal')?.addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeHelp();
});

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeHelp();
});

// textarea 自动高度
document.getElementById('messageInput')?.addEventListener('input', autoResizeTextarea);

// ===== 消息渲染 =====

/** 滚动到底部 */
function scrollToBottom() {
    const container = document.getElementById('chatMessages');
    container.scrollTop = container.scrollHeight;
}

/** 添加系统消息（居中提示） */
function addSystemMessage(text) {
    const container = document.getElementById('chatMessages');
    const div = document.createElement('div');
    div.className = 'round-transition';
    div.innerHTML = `
        <div class="round-transition-icon">💬</div>
        <div class="round-transition-desc">${escapeHtml(text)}</div>
    `;
    container.appendChild(div);
    scrollToBottom();
}

/** 添加用户消息 */
function addUserMessage(text) {
    const container = document.getElementById('chatMessages');
    const div = document.createElement('div');
    div.className = 'message user';
    div.innerHTML = `
        <div class="message-avatar">
            <svg viewBox="0 0 24 24"><path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>
        </div>
        <div class="message-body">
            <div class="message-content"><p>${escapeHtml(text)}</p></div>
        </div>
    `;
    container.appendChild(div);
    scrollToBottom();
}

/** 添加 AI 消息（带可选 Tips） */
function addAIMessage(content, tips) {
    const container = document.getElementById('chatMessages');
    const div = document.createElement('div');
    div.className = 'message ai';

    const tipsHtml = tips ? `
        <div class="message-tips ${state.tipsEnabled ? '' : 'hidden'}">
            <div class="tips-header" onclick="toggleTipsCollapse(this)">
                <div class="tips-header-left">
                    <svg viewBox="0 0 24 24"><path d="M9 21c0 .55.45 1 1 1h4c.55 0 1-.45 1-1v-1H9v1zm3-19C8.14 2 5 5.14 5 9c0 2.38 1.19 4.47 3 5.74V17c0 .55.45 1 1 1h6c.55 0 1-.45 1-1v-2.26c1.81-1.27 3-3.36 3-5.74 0-3.86-3.14-7-7-7zm2.85 11.1l-.85.6V16h-4v-2.3l-.85-.6A4.997 4.997 0 017 9c0-2.76 2.24-5 5-5s5 2.24 5 5c0 1.63-.8 3.16-2.15 4.1z"/></svg>
                    <span>答题提示</span>
                </div>
                <span class="tips-toggle-icon">▾</span>
            </div>
            <div class="tips-body">${escapeHtml(tips)}</div>
        </div>
    ` : '';

    div.innerHTML = `
        <div class="message-avatar">
            ${AI_AVATAR_SVG}
        </div>
        <div class="message-body">
            <div class="message-content">${formatContent(content)}</div>
            ${tipsHtml}
        </div>
    `;
    container.appendChild(div);
    scrollToBottom();
    return div;
}

/** 添加思考中指示器 */
function addThinkingIndicator() {
    const container = document.getElementById('chatMessages');
    const div = document.createElement('div');
    div.className = 'message ai';
    div.id = 'thinking-indicator';
    div.innerHTML = `
        <div class="message-avatar">
            ${AI_AVATAR_SVG}
        </div>
        <div class="message-body">
            <div class="book-loading">
                <div class="book">
                    <div class="book-page"></div>
                    <div class="book-page"></div>
                    <div class="book-page"></div>
                </div>
                <span class="loading-text">思考中</span>
                <span class="loading-dots"><span></span><span></span><span></span></span>
            </div>
        </div>
    `;
    container.appendChild(div);
    scrollToBottom();
    return 'thinking-indicator';
}

/** 移除思考中指示器 */
function removeThinkingIndicator() {
    const el = document.getElementById('thinking-indicator');
    if (el) el.remove();
}

/** 创建流式消息容器 */
function createStreamMessage() {
    const container = document.getElementById('chatMessages');
    const id = 'stream-' + Date.now();
    const div = document.createElement('div');
    div.className = 'message ai';
    div.id = id;
    div.innerHTML = `
        <div class="message-avatar">
            ${AI_AVATAR_SVG}
        </div>
        <div class="message-body">
            <div class="message-thinking" id="${id}-thinking" style="display: none;">
                <div class="thinking-header">
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 17h-2v-2h2v2zm2.07-7.75l-.9.92C13.45 12.9 13 13.5 13 15h-2v-.5c0-1.1.45-2.1 1.17-2.83l1.24-1.26c.37-.36.59-.86.59-1.41 0-1.1-.9-2-2-2s-2 .9-2 2H8c0-2.21 1.79-4 4-4s4 1.79 4 4c0 .88-.36 1.68-.93 2.25z"/></svg>
                    <span>思考过程</span>
                    <span class="thinking-toggle">点击展开/折叠</span>
                </div>
                <div class="thinking-content" id="${id}-thinking-content"></div>
            </div>
            <div class="message-content" id="${id}-content">
                <div class="book-loading">
                    <div class="book">
                        <div class="book-page"></div>
                        <div class="book-page"></div>
                        <div class="book-page"></div>
                    </div>
                    <span class="loading-text">思考中</span>
                    <span class="loading-dots"><span></span><span></span><span></span></span>
                </div>
            </div>
        </div>
    `;
    container.appendChild(div);
    scrollToBottom();
    return id;
}

/** 更新流式消息内容 */
function updateStreamMessage(id, thinking, content, isThinking) {
    const thinkingDiv = document.getElementById(id + '-thinking');
    const thinkingContent = document.getElementById(id + '-thinking-content');
    const contentDiv = document.getElementById(id + '-content');

    if (thinking && thinkingDiv) {
        thinkingDiv.style.display = 'block';
        thinkingContent.textContent = thinking;
    }

    if (content && contentDiv) {
        contentDiv.innerHTML = formatContent(content) + '<span class="typing-cursor">▊</span>';
    }

    scrollToBottom();
}

/** 完成流式消息 */
function finalizeStreamMessage(id, thinking, content, tips) {
    const el = document.getElementById(id);
    if (!el) return;

    const thinkingDiv = document.getElementById(id + '-thinking');
    const contentEl = document.getElementById(id + '-content');

    if (!thinking && thinkingDiv) {
        thinkingDiv.remove();
    }

    if (contentEl) {
        contentEl.innerHTML = formatContent(content);
    }

    if (thinking && thinkingDiv) {
        thinkingDiv.onclick = function() {
            this.classList.toggle('collapsed');
        };
    }

    // 添加 Tips
    if (tips) {
        const body = el.querySelector('.message-body');
        const tipsDiv = document.createElement('div');
        tipsDiv.className = 'message-tips ' + (state.tipsEnabled ? '' : 'hidden');
        tipsDiv.innerHTML = `
            <div class="tips-header" onclick="toggleTipsCollapse(this)">
                <div class="tips-header-left">
                    <svg viewBox="0 0 24 24"><path d="M9 21c0 .55.45 1 1 1h4c.55 0 1-.45 1-1v-1H9v1zm3-19C8.14 2 5 5.14 5 9c0 2.38 1.19 4.47 3 5.74V17c0 .55.45 1 1 1h6c.55 0 1-.45 1-1v-2.26c1.81-1.27 3-3.36 3-5.74 0-3.86-3.14-7-7-7zm2.85 11.1l-.85.6V16h-4v-2.3l-.85-.6A4.997 4.997 0 017 9c0-2.76 2.24-5 5-5s5 2.24 5 5c0 1.63-.8 3.16-2.15 4.1z"/></svg>
                    <span>答题提示</span>
                </div>
                <span class="tips-toggle-icon">▾</span>
            </div>
            <div class="tips-body">${escapeHtml(tips)}</div>
        `;
        body.appendChild(tipsDiv);
    }

    scrollToBottom();
}

/** 切换 Tips 折叠 */
function toggleTipsCollapse(header) {
    const body = header.nextElementSibling;
    const icon = header.querySelector('.tips-toggle-icon');
    body.classList.toggle('collapsed');
    icon.classList.toggle('collapsed');
}

/** 轮次切换卡片 */
function addRoundTransition(newRound) {
    const container = document.getElementById('chatMessages');
    const div = document.createElement('div');
    div.className = 'round-transition';
    const roundName = newRound === 2 ? 'Leader 面' : '技术面';
    div.innerHTML = `
        <div class="round-transition-icon">🔄</div>
        <div class="round-transition-title">第${newRound - 1}轮面试结束</div>
        <div class="round-transition-desc">即将进入第${newRound}轮 · ${roundName}，回复任意内容开始</div>
    `;
    container.appendChild(div);
    scrollToBottom();
}

/** 面试结束卡片 */
function addInterviewEndCard(analyzing = true) {
    const container = document.getElementById('chatMessages');
    const div = document.createElement('div');
    div.className = 'interview-end';
    div.id = 'interview-end-card';
    div.innerHTML = `
        <div class="interview-end-icon">✅</div>
        <div class="interview-end-title">面试结束！</div>
        <div class="interview-end-desc" id="endDesc">${analyzing ? '正在生成分析报告...' : '分析报告已生成'}</div>
        <button class="report-btn" id="reportBtn" ${analyzing ? 'disabled' : ''} onclick="viewReport()">
            查看分析报告
        </button>
        ${analyzing ? '<div class="report-loading">预计需要 30-60 秒，请稍候...</div>' : ''}
    `;
    container.appendChild(div);
    scrollToBottom();
}

/** 更新面试结束卡片状态 */
function updateInterviewEndCard(analyzing) {
    const desc = document.getElementById('endDesc');
    const btn = document.getElementById('reportBtn');
    const loading = document.querySelector('.report-loading');
    if (desc) desc.textContent = analyzing ? '正在生成分析报告...' : '分析报告已生成';
    if (btn) btn.disabled = analyzing;
    if (loading && !analyzing) loading.remove();
}

/** 跳转分析报告 */
function viewReport() {
    window.location.href = `ai-interview-report.html?session_id=${state.sessionId}`;
}

// ===== 工具函数 =====

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatContent(text) {
    if (!text) return '';
    return escapeHtml(text)
        .replace(/\n/g, '<br>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
}

// ===== SSE 流式对话 =====

/** 开始面试（请求 AI 开场白） */
async function startInterview() {
    const token = localStorage.getItem('token');
    if (!token || !state.sessionId) return;

    state.isStreaming = true;
    disableInput();
    const thinkingId = addThinkingIndicator();

    try {
        const response = await fetch(`${API_BASE}/interview/${state.sessionId}/stream`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
                message: '',
                history: [],
                round: state.round
            })
        });

        if (!response.ok) {
            throw new Error(`请求失败 (${response.status})`);
        }

        removeThinkingIndicator();
        await processSSEStream(response);

    } catch (err) {
        removeThinkingIndicator();
        addAIMessage(`❌ 连接失败：${err.message}。请刷新页面重试。`);
        showToast('连接失败', true);
    } finally {
        state.isStreaming = false;
        enableInput();
    }
}

/** 发送用户消息 */
async function sendMessage() {
    if (state.paused || state.isStreaming || state.interviewEnded) return;

    const input = document.getElementById('messageInput');
    const text = input.value.trim();
    if (!text) return;

    // 添加用户消息
    addUserMessage(text);
    state.chatHistory.push({ role: 'user', content: text });
    clearInput();

    // 如果正在等待轮次切换
    if (state.roundSwitched) {
        state.roundSwitched = false;
        state.round = 2;
        updateRoundDisplay();
    }

    state.questionCount++;
    updateQuestionCount();

    // 流式请求 AI 回复
    state.isStreaming = true;
    disableInput();
    const thinkingId = addThinkingIndicator();

    const token = localStorage.getItem('token');

    try {
        const response = await fetch(`${API_BASE}/interview/${state.sessionId}/stream`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
                message: text,
                history: state.chatHistory,
                round: state.round
            })
        });

        if (!response.ok) {
            throw new Error(`请求失败 (${response.status})`);
        }

        removeThinkingIndicator();
        await processSSEStream(response);

    } catch (err) {
        removeThinkingIndicator();
        addAIMessage(`❌ 请求失败：${err.message}`);
        showToast('请求失败', true);
    } finally {
        state.isStreaming = false;
        if (!state.interviewEnded && !state.roundSwitched) {
            enableInput();
        }
    }
}

/** 处理 SSE 流 */
async function processSSEStream(response) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let thinkingText = '';
    let contentText = '';
    let tipsText = '';
    let streamId = null;
    let isContent = false;
    let isTips = false;

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
            if (!line.startsWith('data: ')) continue;

            const jsonStr = line.slice(6);
            if (jsonStr === '[DONE]') continue;

            try {
                const data = JSON.parse(jsonStr);

                // 思考过程
                if (data.type === 'thinking') {
                    if (!streamId) {
                        streamId = createStreamMessage();
                    }
                    thinkingText += data.data;
                    updateStreamMessage(streamId, thinkingText, contentText, true);
                }

                // 流式内容
                if (data.type === 'content') {
                    if (!streamId) {
                        streamId = createStreamMessage();
                    }
                    contentText += data.data;
                    updateStreamMessage(streamId, thinkingText, contentText, false);
                    isContent = true;
                }

                // Tips 提示
                if (data.type === 'tips') {
                    tipsText += data.data;
                    isTips = true;
                }

                // 轮次切换标记
                if (data.type === 'round_end') {
                    if (streamId) {
                        finalizeStreamMessage(streamId, thinkingText, contentText, tipsText || null);
                        state.chatHistory.push({ role: 'assistant', content: contentText });
                    }
                    addRoundTransition(state.round + 1);
                    state.roundSwitched = true;
                    state.round = 2;
                    updateRoundDisplay();
                    thinkingText = '';
                    contentText = '';
                    tipsText = '';
                    streamId = null;
                }

                // 面试结束标记
                if (data.type === 'interview_end') {
                    if (streamId) {
                        finalizeStreamMessage(streamId, thinkingText, contentText, tipsText || null);
                        state.chatHistory.push({ role: 'assistant', content: contentText });
                    }
                    state.interviewEnded = true;
                    addInterviewEndCard(true);
                    // 触发分析
                    triggerAnalysis();
                }

            } catch (e) {
                console.warn('SSE 解析失败:', e, data);
            }
        }
    }

    // 流正常结束（非轮次切换/面试结束）
    if (streamId && !state.roundSwitched && !state.interviewEnded) {
        finalizeStreamMessage(streamId, thinkingText, contentText, tipsText || null);
        state.chatHistory.push({ role: 'assistant', content: contentText });
    }
}

/** 触发分析报告生成 */
async function triggerAnalysis() {
    const token = localStorage.getItem('token');
    try {
        const response = await fetch(`${API_BASE}/interview/${state.sessionId}/analyze`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (response.ok) {
            updateInterviewEndCard(false);
            showToast('分析报告已生成');
        } else {
            updateInterviewEndCard(false);
            showToast('分析完成，点击按钮查看');
        }
    } catch (err) {
        updateInterviewEndCard(false);
        showToast('分析请求失败，请稍后重试', true);
    }
}
