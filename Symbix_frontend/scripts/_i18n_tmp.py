import sys

p = 'src/pages/chat_window.vue'
s = open(p, encoding='utf-8').read()

replacements = [
    ("'重连成功'", "t('mcpPanel.reconnectSuccess')"),
    ("`重连失败:${e.message || e}`", "t('mcpPanel.reconnectFail', { msg: e.message || e })"),
    ("`已删除 ${serverId}`", "t('mcpPanel.removeSuccess', { serverId })"),
    ("`删除失败:${e.message || e}`", "t('mcpPanel.removeFail', { msg: e.message || e })"),
    ("`已删除 ${skillName}`", "t('skillPanel.deleteSuccess', { name: skillName })"),
    ("`删除 Skill 失败:${e.message || e}`", "t('skillPanel.deleteFail', { msg: e.message || e })"),
    ("`MCP 连接正常:${connected}/${entries.length} 个 Server 在线`", "t('mcpPanel.testOk', { connected, total: entries.length })"),
    ("'尚未配置任何 MCP Server'", "t('mcpPanel.testNoConfig')"),
    ("'MCP 已配置但当前均未连通'", "t('mcpPanel.testWarning')"),
    ("'无法连接到 MCP 服务 (HTTP ' + res.status + ')'", "t('mcpPanel.testFail', { status: res.status })"),
    ("'无法连接到 MCP 服务: ' + (err.message || err)", "t('mcpPanel.testFailDetail', { msg: err.message || err })"),
    ("'Skill 列表已刷新'", "t('skillPanel.refreshSuccess')"),
    ("'获取 Skill 列表失败 (HTTP ' + res.status + ')'", "t('skillPanel.fetchFail', { status: res.status })"),
    ("'获取 Skill 列表失败: ' + (err.message || err)", "t('skillPanel.fetchFailDetail', { msg: err.message || err })"),
    ("'获取 Skill 列表失败'", "t('skillPanel.fetchFailShort')"),
    ("'获取 Native Tools 列表失败'", "t('nativeToolsPanel.fetchFail')"),
    ("'获取 MCP 配置失败'", "t('mcpPanel.fetchConfigFail')"),
    ("publishAgentStatus('idle', '已暂停')", "publishAgentStatus('idle', t('chat.stopGenerate'))"),
    ("publishAgentStatus('thinking', '我来看看...')", "publishAgentStatus('thinking', t('chat.thinking'))"),
    ("publishAgentStatus('error', '处理时遇到了一点问题')", "publishAgentStatus('error', t('chat.errorOccurred'))"),
    ("`请求失败:${e.message}`", "t('chat.requestFail', { msg: e.message })"),
    ("publishAgentStatus('thinking', approved ? '继续处理...' : '正在整理结果...')", "publishAgentStatus('thinking', approved ? t('chat.continueProcessing') : t('chat.processingResult'))"),
    ("publishAgentStatus('complete', approved ? '完成啦!' : '已处理完毕')", "publishAgentStatus('complete', approved ? t('chat.complete') : t('chat.processedDone'))"),
    ("publishAgentStatus('error', '审批处理失败')", "publishAgentStatus('error', t('chat.approvalFailed'))"),
    ("console.error('审批失败:', e)", "console.error(t('chat.approvalFailed'), e)"),
    ("`审批失败:${e.message}`", "t('chat.approvalFailedDetail', { msg: e.message })"),
]

for old, new in replacements:
    if old in s:
        s = s.replace(old, new)
        print(f"OK: {old[:50]}")
    else:
        print(f"MISS: {old[:50]}")

open(p, 'w', encoding='utf-8', newline='').write(s)
print("\nDone!")
