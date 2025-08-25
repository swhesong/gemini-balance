// 批量密钥检测功能
document.addEventListener('DOMContentLoaded', function() {
    // 从localStorage恢复设置
    const savedApiBaseUrl = localStorage.getItem('batchVerify_apiBaseUrl');
    const savedTestModel = localStorage.getItem('batchVerify_testModel');
    
    if (savedApiBaseUrl) {
        document.getElementById('apiBaseUrl').value = savedApiBaseUrl;
    }
    
    if (savedTestModel) {
        document.getElementById('testModel').value = savedTestModel;
    }
});

async function checkTokens() {
    const tokensTextarea = document.getElementById('tokensTextarea');
    const checkButton = document.getElementById('checkButton');
    const validResults = document.getElementById('validResults');
    const invalidResults = document.getElementById('invalidResults');
    const duplicateResults = document.getElementById('duplicateResults');
    const validButtons = document.getElementById('validButtons');
    
    const testModel = document.getElementById('testModel').value.trim();

    // 保存设置到localStorage (API地址不再需要)
    localStorage.setItem('batchVerify_testModel', testModel);

    if (!testModel) {
        showAlert('请填写有效的测试模型', 'warning');
        return;
    }

    const inputText = tokensTextarea.value.trim();
    if (!inputText) {
        showAlert('请输入至少一个 API Key', 'warning');
        return;
    }

    // 解析输入的密钥
    const rawTokens = inputText.replace(/[\n,]+/g, ' ').split(' ');
    let allTokens = rawTokens.map(t => t.trim()).filter(t => t !== '');

    // 检测重复
    let tokenCount = new Map();
    let duplicateTokens = new Set();
    
    allTokens.forEach(token => {
        tokenCount.set(token, (tokenCount.get(token) || 0) + 1);
        if (tokenCount.get(token) > 1) {
            duplicateTokens.add(token);
        }
    });

    const uniqueTokens = [...new Set(allTokens)];

    // 显示重复结果
    duplicateResults.textContent = duplicateTokens.size > 0 
        ? `发现 ${duplicateTokens.size} 个重复Key:\n${[...duplicateTokens].join('\n')}\n\n(检测时已自动去重)` 
        : '没有发现重复的Key';

    // 开始检测
    checkButton.disabled = true;
    checkButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> 检测中...';
    validResults.textContent = '';
    invalidResults.innerHTML = '';
    validButtons.style.display = 'none';

    try {
        // 调用新的无状态批量验证接口
        const response = await fetch('/v1beta/batch-verify-stateless', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ keys: uniqueTokens })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            const errorMessage = errorData.error || `HTTP ${response.status} - ${response.statusText}`;
            throw new Error(errorMessage);
        }

        const data = await response.json();
        const validTokens = data.successful_keys || [];
        const failedKeys = data.failed_keys || {};

        // 显示有效密钥
        validResults.textContent = validTokens.join('\n');

        // 显示无效密钥
        invalidResults.innerHTML = '';
        Object.entries(failedKeys).forEach(([token, error]) => {
            const div = document.createElement('div');
            div.className = 'invalid-token';
            div.innerHTML = `
                <div class="invalid-token-token">${escapeHtml(token)}</div>
                <div class="invalid-token-message">错误: ${escapeHtml(error)}</div>
            `;
            invalidResults.appendChild(div);
        });

        // 显示复制按钮
        if (validTokens.length > 0) {
            validButtons.style.display = 'block';
        } else {
            validButtons.style.display = 'none';
        }

        // 显示结果统计
        showAlert(
            `检测完成！有效: ${validTokens.length}，无效: ${Object.keys(failedKeys).length}，重复: ${duplicateTokens.size}`,
            'success'
        );

    } catch (error) {
        showAlert(`检测过程中出现错误: ${error.message}`, 'danger');
    } finally {
        checkButton.disabled = false;
        checkButton.innerHTML = '<i class="fas fa-play"></i> 开始检测';
    }
}

function copyTokens(type) {
    const resultsDiv = document.getElementById('validResults');
    const textToCopy = resultsDiv.textContent.trim();

    if (!textToCopy) {
        showAlert('没有可复制的有效密钥', 'warning');
        return;
    }

    // HTTP环境下直接使用传统复制方法
    fallbackCopyTextToClipboard(textToCopy, '有效密钥已复制到剪贴板 (换行分隔)');
}

function copyTokensWithComma(type) {
    const resultsDiv = document.getElementById('validResults');
    const tokens = resultsDiv.textContent.trim().split('\n').filter(t => t.trim());
    const textToCopy = tokens.join(',');

    if (!textToCopy) {
        showAlert('没有可复制的有效密钥', 'warning');
        return;
    }

    // HTTP环境下直接使用传统复制方法
    fallbackCopyTextToClipboard(textToCopy, '有效密钥已复制到剪贴板 (逗号分隔)');
}

function showAlert(message, type) {
    // 创建现代化的通知框
    const alertDiv = document.createElement('div');
    const bgColor = type === 'success' ? 'bg-green-500' :
                   type === 'warning' ? 'bg-yellow-500' :
                   type === 'danger' ? 'bg-red-500' : 'bg-blue-500';

    alertDiv.className = `fixed top-4 right-4 ${bgColor} text-white px-6 py-4 rounded-lg shadow-lg z-50 max-w-md animate-fade-in`;
    alertDiv.innerHTML = `
        <div class="flex items-center justify-between">
            <span class="text-sm font-medium">${message}</span>
            <button onclick="this.parentElement.parentElement.remove()" class="ml-4 text-white hover:text-gray-200">
                <i class="fas fa-times"></i>
            </button>
        </div>
    `;

    // 插入到页面
    document.body.appendChild(alertDiv);

    // 3秒后自动消失
    setTimeout(() => {
        if (alertDiv.parentNode) {
            alertDiv.remove();
        }
    }, 3000);
}

function fallbackCopyTextToClipboard(text, successMessage) {
    // 创建临时文本区域
    const textArea = document.createElement("textarea");
    textArea.value = text;

    // 避免滚动到底部
    textArea.style.top = "0";
    textArea.style.left = "0";
    textArea.style.position = "fixed";
    textArea.style.opacity = "0";

    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();

    try {
        const successful = document.execCommand('copy');
        if (successful) {
            showAlert(successMessage, 'success');
        } else {
            showAlert('复制失败，请手动复制', 'danger');
        }
    } catch (err) {
        console.error('Fallback copy failed:', err);
        showAlert('复制失败，请手动复制', 'danger');
    }

    document.body.removeChild(textArea);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
