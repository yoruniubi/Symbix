// One-off codemod: replace hardcoded Chinese UI strings with i18n $t()/t() calls.
const fs = require('fs')
const path = require('path')
const root = path.join(__dirname, '..', 'src')

const edits = []

function rep(file, search, replace) {
  edits.push({ file, search, replace })
}

/* ---------- FilePanel.vue ---------- */
const FP = 'components/panels/FilePanel.vue'
rep(FP, '<span class="side-panel-title">文件浏览器</span>', `<span class="side-panel-title">{{ $t('filePanel.title') }}</span>`)
rep(FP, `title="选择电脑上的目录" @click="chooseDirectory">打开目录</button>`, `:title="$t('filePanel.openDir')" @click="chooseDirectory">{{ $t('filePanel.openDir') }}</button>`)
rep(FP, `title="刷新" @click="loadDirectory(currentPath)"`, `:title="$t('filePanel.refresh')" @click="loadDirectory(currentPath)"`)
rep(FP, `title="关闭" @click="emit('update:activePanel', null)"`, `:title="$t('filePanel.close')" @click="emit('update:activePanel', null)"`)
rep(FP, `<button type="button" @click="loadDirectory('.')">项目</button>`, `<button type="button" @click="loadDirectory('.')">{{ $t('filePanel.project') }}</button>`)
rep(FP, `<div v-if="loading" class="empty">加载中...</div>`, `<div v-if="loading" class="empty">{{ $t('filePanel.loading') }}</div>`)
rep(FP, `<span>↩</span><span>返回上级</span>`, `<span>↩</span><span>{{ $t('filePanel.backParent') }}</span>`)
rep(FP, `<div v-if="entries.length === 0" class="empty">此文件夹为空</div>`, `<div v-if="entries.length === 0" class="empty">{{ $t('filePanel.empty') }}</div>`)
rep(FP, `<button type="button" @click="saveFile">保存</button>`, `<button type="button" @click="saveFile">{{ $t('filePanel.save') }}</button>`)
rep(FP, `<button type="button" @click="deleteFile">删除</button>`, `<button type="button" @click="deleteFile">{{ $t('filePanel.delete') }}</button>`)
// script
rep(FP, `const { width: panelWidth`, `const { t } = useI18n()\nconst { width: panelWidth`)
rep(FP, `import { useResizablePanel } from '@/composables/useResizablePanel'`, `import { useI18n } from 'vue-i18n'\nimport { useResizablePanel } from '@/composables/useResizablePanel'`)
rep(FP, `const externalRootName = computed(() => externalRoot.value.split(/[\\\\/]/).filter(Boolean).pop() || '电脑目录')`, `const externalRootName = computed(() => externalRoot.value.split(/[\\\\/]/).filter(Boolean).pop() || t('filePanel.computerDir'))`)
rep(FP, `throw new Error(data.detail || \`请求失败 (\${response.status})\`)`, `throw new Error(data.detail || t('filePanel.requestError', { status: response.status }))`)
rep(FP, `error.value = err.message || '目录加载失败'`, `error.value = err.message || t('filePanel.loadError')`)
rep(FP, `const selected = await open({ directory: true, multiple: false, title: '选择要浏览的目录' })`, `const selected = await open({ directory: true, multiple: false, title: t('filePanel.openDirTitle') })`)
rep(FP, `error.value = '当前环境无法打开系统目录选择框,请使用桌面版 Tauri。'`, `error.value = t('filePanel.envError')`)
rep(FP, `error.value = err.message || '文件读取失败'`, `error.value = err.message || t('filePanel.fileReadError')`)
rep(FP, `error.value = err.message || '文件保存失败'`, `error.value = err.message || t('filePanel.fileSaveError')`)
rep(FP, `if (!window.confirm(\`确定删除「\${selectedFile.value.name}」吗?\`)) return`, `if (!window.confirm(t('filePanel.deleteConfirm', { name: selectedFile.value.name }))) return`)
rep(FP, `error.value = err.message || '文件删除失败'`, `error.value = err.message || t('filePanel.fileDeleteError')`)

/* ---------- SkillPanel.vue ---------- */
const SP = 'components/panels/SkillPanel.vue'
rep(SP, '<span class="side-panel-title">Skill 面板</span>', `<span class="side-panel-title">{{ $t('skillPanel.title') }}</span>`)
rep(SP, `>\n            添加\n          </n-button>`, `>\n            {{ $t('skillPanel.add') }}\n          </n-button>`)
rep(SP, `已安装 {{ skillList.length }} 个 Skill({{ skillToolList.length }} 个工具)`, `{{ $t('skillPanel.installed', { count: skillList.length, toolCount: skillToolList.length }) }}`)
rep(SP, `🔧 工具: skill__{{ skill.name }}`, `{{ $t('skillPanel.tool', { name: 'skill__' + skill.name }) }}`)
rep(SP, `title="删除 Skill"`, `:title="$t('skillPanel.delete')"`)
rep(SP, `>\n          刷新列表\n        </n-button>`, `>\n          {{ $t('skillPanel.refresh') }}\n        </n-button>`)
rep(SP, `description="暂无 Skill"`, `:description="$t('skillPanel.empty')"`)

/* ---------- McpPanel.vue ---------- */
const MP = 'components/panels/McpPanel.vue'
rep(MP, '<span class="side-panel-title">MCP 面板</span>', `<span class="side-panel-title">{{ $t('mcpPanel.title') }}</span>`)
rep(MP, `>\n            添加\n          </n-button>`, `>\n            {{ $t('mcpPanel.add') }}\n          </n-button>`)
rep(MP, `{{ mcpServerGroups.length }} 个 Server · {{ mcpToolList.length }} 个工具`, `{{ $t('mcpPanel.summary', { count: mcpServerGroups.length, toolCount: mcpToolList.length }) }}`)
rep(MP, `title="重连"`, `:title="$t('mcpPanel.reconnect')"`)
rep(MP, `title="删除"`, `:title="$t('mcpPanel.delete')"`)
rep(MP, `{{ group.tool_count }} 工具`, `{{ group.tool_count }} {{ $t('mcpPanel.toolUnit') }}`)
rep(MP, `description="未连接任何 MCP Server"`, `:description="$t('mcpPanel.empty')"`)
rep(MP, `>\n          测试连接\n        </n-button>`, `>\n          {{ $t('mcpPanel.testConnection') }}\n        </n-button>`)
// script
rep(MP, `import { useResizablePanel } from '@/composables/useResizablePanel'`, `import { useI18n } from 'vue-i18n'\nimport { useResizablePanel } from '@/composables/useResizablePanel'`)
rep(MP, `const { width: panelWidth`, `const { t } = useI18n()\nconst { width: panelWidth`)
rep(MP, `if (!info) return '未知'`, `if (!info) return t('mcpPanel.statusUnknown')`)
rep(MP, `if (info.status === 'connected') return \`已连接 · \${info.tools_count ?? 0} 工具\``, `if (info.status === 'connected') return t('mcpPanel.statusConnected', { count: info.tools_count ?? 0 })`)
rep(MP, `if (info.status === 'error') return info.error || '错误'`, `if (info.status === 'error') return info.error || t('mcpPanel.statusError')`)
rep(MP, `return info.status || '未连接'`, `return info.status || t('mcpPanel.statusOffline')`)

/* ---------- NativeToolsPanel.vue ---------- */
const NT = 'components/panels/NativeToolsPanel.vue'
rep(NT, '<span class="side-panel-title">Native Tools 面板</span>', `<span class="side-panel-title">{{ $t('nativeToolsPanel.title') }}</span>`)
rep(NT, `已注册 {{ nativeToolList.length }} 个内置工具`, `{{ $t('nativeToolsPanel.summary', { count: nativeToolList.length }) }}`)
rep(NT, `description="暂无内置工具"`, `:description="$t('nativeToolsPanel.empty')"`)

/* ---------- ChatActivityBar.vue ---------- */
const AB = 'components/ChatActivityBar.vue'
rep(AB, `import { useRouter } from 'vue-router'`, `import { useRouter } from 'vue-router'\nimport { useI18n } from 'vue-i18n'`)
rep(AB, `const router = useRouter()`, `const router = useRouter()\nconst { t } = useI18n()`)
rep(AB, `        模型设置\n      </n-tooltip>`, `        {{ $t('activityBar.modelSettings') }}\n      </n-tooltip>`)
rep(AB, `{ panel: 'files', label: '文件浏览器' },`, `{ panel: 'files', label: t('activityBar.files') },`)
rep(AB, `{ panel: 'skill', label: 'Skill' },`, `{ panel: 'skill', label: t('activityBar.skill') },`)
rep(AB, `{ panel: 'mcp', label: 'MCP' },`, `{ panel: 'mcp', label: t('activityBar.mcp') },`)
rep(AB, `{ panel: 'native_tools', label: 'Native Tools' },`, `{ panel: 'native_tools', label: t('activityBar.nativeTools') },`)

/* ---------- ChatInput.vue ---------- */
const CI = 'components/ChatInput.vue'
rep(CI, `placeholder="输入消息,Enter 发送,Shift+Enter 换行..."`, `:placeholder="$t('chatInput.placeholder')"`)

/* ============================== APPLY ============================== */
const byFile = new Map()
for (const e of edits) {
  if (!byFile.has(e.file)) byFile.set(e.file, [])
  byFile.get(e.file).push(e)
}

let totalOk = 0, totalFail = 0
for (const [file, list] of byFile) {
  const abs = path.join(root, file)
  let s = fs.readFileSync(abs, 'utf8')
  let fail = 0
  for (const { search, replace } of list) {
    if (s.includes(search)) {
      s = s.split(search).join(replace)
      totalOk++
    } else {
      fail++
      totalFail++
      console.log(`  MISS [${file}]: ${JSON.stringify(search.slice(0, 60))}`)
    }
  }
  if (fail === 0 || true) fs.writeFileSync(abs, s)
  console.log(`${file}: ${list.length - fail}/${list.length} applied${fail ? '  <-- has misses' : ''}`)
}
console.log(`\nTOTAL: ${totalOk} applied, ${totalFail} missed`)
