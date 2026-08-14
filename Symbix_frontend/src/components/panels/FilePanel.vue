<template>
  <transition name="panel-slide">
    <div v-if="activePanel === 'files'" class="side-panel" :class="{ 'is-resizing': isResizing }" :style="{ width: `${panelWidth}px` }">
      <div class="panel-resize-handle" :title="$t('common.pullToResize')" @mousedown="startResize" />
      <div class="side-panel-header">
        <div class="side-panel-actions">
          <n-button size="tiny" type="primary" class="add-entry-btn" :title="$t('filePanel.openDir')" @click="chooseDirectory">
            <template #icon>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
              </svg>
            </template>
            {{ $t('filePanel.openDir') }}
          </n-button>
          <n-button quaternary size="tiny" class="panel-icon-btn" :title="$t('filePanel.refresh')" @click="loadDirectory(currentPath)">
            <svg :class="['refresh-icon', { spinning: loading }]" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
            </svg>
          </n-button>
          <n-button quaternary size="tiny" class="panel-icon-btn close-btn" :title="$t('filePanel.close')" @click="emit('update:activePanel', null)">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
          </n-button>
        </div>
      </div>

      <div class="breadcrumb">
        <!-- 项目根目录 -->
        <button type="button" class="breadcrumb-item" :class="{ active: currentPath === '.' }" @click="loadDirectory('.')">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;">
            <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
            <polyline points="9 22 9 12 15 12 15 22"/>
          </svg>
          <span>{{ $t('filePanel.project') }}</span>
        </button>
        <template v-if="isExternalPath">
          <span class="breadcrumb-sep">/</span>
          <button type="button" class="breadcrumb-item" @click="loadDirectory(externalRoot)">{{ externalRootName }}</button>
        </template>
        <template v-for="(part, index) in breadcrumbParts" :key="`${part}-${index}`">
          <span class="breadcrumb-sep">/</span>
          <button type="button" class="breadcrumb-item" @click="loadBreadcrumb(index)">{{ part }}</button>
        </template>
      </div>

      <div class="side-panel-body">
        <div v-if="error" class="error">{{ error }}</div>
        <div v-if="loading && entries.length === 0" class="empty">{{ $t('filePanel.loading') }}</div>

        <div v-else class="file-list">
          <button
            v-if="currentPath !== '.'"
            type="button"
            class="file-row back-row"
            @click="loadDirectory(parentPath)"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;">
              <line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>
            </svg>
            <span>{{ $t('filePanel.backParent') }}</span>
          </button>

          <button
            v-for="entry in entries"
            :key="entry.path"
            type="button"
            class="file-row"
            :class="{ 'is-dir': entry.type === 'directory' }"
            @click="openEntry(entry)"
          >
            <span class="file-icon">
              <svg v-if="entry.type === 'directory'" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
              </svg>
              <svg v-else width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
              </svg>
            </span>
            <span class="file-name">{{ entry.name }}</span>
            <small v-if="entry.type === 'file'">{{ formatSize(entry.size) }}</small>
          </button>

          <div v-if="entries.length === 0" class="empty">{{ $t('filePanel.empty') }}</div>
        </div>
      </div>

      <div v-if="selectedFile" class="editor">
        <div class="editor-header">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0; opacity:0.7;">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
          </svg>
          <span class="editor-filename">{{ selectedFile.name }}</span>
          <div class="editor-actions">
            <n-button size="tiny" type="primary" @click="saveFile">{{ $t('filePanel.save') }}</n-button>
            <n-button size="tiny" quaternary type="error" @click="deleteFile">{{ $t('filePanel.delete') }}</n-button>
          </div>
        </div>
        <textarea v-model="selectedFile.content" spellcheck="false" />
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useResizablePanel } from '@/composables/useResizablePanel'

type Panel = 'files' | 'skill' | 'mcp' | 'native_tools'
type FileEntry = {
  name: string
  path: string
  type: 'file' | 'directory'
  size: number | null
}
type SelectedFile = { name: string; path: string; content: string }

const props = defineProps<{ activePanel: Panel | null }>()
const emit = defineEmits<{
  (event: 'update:activePanel', value: Panel | null): void
}>()

const backendUrl = 'http://127.0.0.1:8000'
const entries = ref<FileEntry[]>([])
const currentPath = ref('.')
const selectedFile = ref<SelectedFile | null>(null)
const loading = ref(false)
const error = ref('')
const { t } = useI18n()
const { width: panelWidth, isResizing, startResize } = useResizablePanel({
  storageKey: 'symbix-panel-width-files',
})

const pathParts = computed(() => currentPath.value === '.' ? [] : currentPath.value.split('/'))
const isExternalPath = computed(() => /^[a-zA-Z]:[\\/]/.test(currentPath.value) || currentPath.value.startsWith('\\\\'))
const externalRoot = ref('')
const externalRootName = computed(() => externalRoot.value.split(/[\\/]/).filter(Boolean).pop() || t('filePanel.computerDir'))
const breadcrumbParts = computed(() => {
  if (!isExternalPath.value) return pathParts.value
  const root = externalRoot.value.replace(/[\\/]+$/, '')
  return currentPath.value.replace(root, '').split(/[\\/]/).filter(Boolean)
})
const parentPath = computed(() => (
  isExternalPath.value
    ? currentPath.value.replace(/[\\/][^\\/]+$/, '') || externalRoot.value
    : pathParts.value.length <= 1 ? '.' : pathParts.value.slice(0, -1).join('/')
))

async function request(path: string, options?: RequestInit) {
  const response = await fetch(`${backendUrl}${path}`, options)
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.detail || t('filePanel.requestError', { status: response.status }))
  return data
}

async function loadDirectory(path: string) {
  loading.value = true
  error.value = ''
  selectedFile.value = null

  try {
    const data = await request(`/api/files/list?path=${encodeURIComponent(path)}`)
    currentPath.value = data.path || path
    entries.value = data.entries || []
  } catch (err: any) {
    error.value = err.message || t('filePanel.loadError')
  } finally {
    loading.value = false
  }
}

async function chooseDirectory() {
  try {
    const { open } = await import('@tauri-apps/plugin-dialog')
    const selected = await open({ directory: true, multiple: false, title: t('filePanel.openDirTitle') })
    if (typeof selected === 'string' && selected) {
      externalRoot.value = selected
      await loadDirectory(selected)
    }
  } catch (err) {
    error.value = t('filePanel.envError')
    console.warn('选择目录失败:', err)
  }
}

function loadBreadcrumb(index: number) {
  if (!isExternalPath.value) {
    loadDirectory(pathParts.value.slice(0, index + 1).join('/'))
    return
  }
  const root = externalRoot.value.replace(/[\\/]+$/, '')
  const suffix = breadcrumbParts.value.slice(0, index + 1).join('/')
  loadDirectory(`${root}/${suffix}`)
}

async function openEntry(entry: FileEntry) {
  if (entry.type === 'directory') {
    await loadDirectory(entry.path)
    return
  }

  try {
    selectedFile.value = await request(`/api/files/read?path=${encodeURIComponent(entry.path)}`)
  } catch (err: any) {
    error.value = err.message || t('filePanel.fileReadError')
  }
}

async function saveFile() {
  if (!selectedFile.value) return

  try {
    await request('/api/files/write', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(selectedFile.value),
    })
  } catch (err: any) {
    error.value = err.message || t('filePanel.fileSaveError')
  }
}

async function deleteFile() {
  if (!selectedFile.value) return
  if (!window.confirm(t('filePanel.deleteConfirm', { name: selectedFile.value.name }))) return

  try {
    await request(`/api/files/item?path=${encodeURIComponent(selectedFile.value.path)}`, {
      method: 'DELETE',
    })
    await loadDirectory(currentPath.value)
  } catch (err: any) {
    error.value = err.message || t('filePanel.fileDeleteError')
  }
}

function formatSize(size: number | null) {
  if (size == null) return ''
  if (size < 1024) return `${size} B`
  return `${(size / 1024).toFixed(1)} KB`
}

watch(() => props.activePanel, (panel) => {
  if (panel === 'files') loadDirectory(currentPath.value)
})

onMounted(() => {
  if (props.activePanel === 'files') loadDirectory('.')
})
</script>

<style scoped>
.side-panel {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  min-width: var(--panel-min-width);
  max-width: min(var(--panel-max-width), 70vw);
  height: 100%;
  min-height: 0;
  background: var(--panel-bg);
  backdrop-filter: blur(16px);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  z-index: 20;
  box-shadow: var(--shadow-md, 0 4px 12px rgba(0, 0, 0, 0.18));
}
.panel-resize-handle {
  position: absolute;
  top: 0;
  right: calc(var(--panel-resize-handle-width) / -2);
  width: var(--panel-resize-handle-width);
  height: 100%;
  cursor: col-resize;
  z-index: 2;
}
.panel-resize-handle:hover,
.is-resizing .panel-resize-handle {
  background: var(--accent-500);
  opacity: 0.35;
}
.panel-slide-enter-active {
  transition: all var(--duration-base, 180ms) var(--ease-standard, ease);
}
.panel-slide-leave-active {
  transition: all var(--duration-fast, 120ms) var(--ease-standard, ease);
}
.panel-slide-enter-from {
  opacity: 0;
  transform: translateX(-20px);
}
.panel-slide-leave-to {
  opacity: 0;
  transform: translateX(-12px);
}

/* ── Header（与其他面板统一） ── */
.side-panel-header {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
  flex: 0 0 auto;
}
.side-panel-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}
.add-entry-btn {
  font-weight: 600 !important;
}
.panel-icon-btn {
  width: 32px !important;
  height: 32px !important;
  min-width: 32px !important;
  padding: 0 !important;
  border-radius: 8px !important;
  flex-shrink: 0;
}
.panel-icon-btn :deep(.n-button__icon) {
  margin: 0 !important;
}
.close-btn:hover {
  color: var(--error, #ef4444) !important;
}

/* ── 面包屑 ── */
.breadcrumb {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 8px 12px;
  overflow-x: auto;
  white-space: nowrap;
  border-bottom: 1px solid var(--border);
  font-size: 12px;
  scrollbar-width: thin;
  flex: 0 0 auto;
}
.breadcrumb::-webkit-scrollbar {
  height: 3px;
}
.breadcrumb::-webkit-scrollbar-thumb {
  background: var(--scrollbar);
  border-radius: 3px;
}
.breadcrumb-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: 0;
  border-radius: 5px;
  padding: 3px 7px;
  cursor: pointer;
  color: var(--text-secondary);
  background: transparent;
  font-size: 12px;
  transition: all 0.15s ease;
  max-width: 140px;
  overflow: hidden;
}
.breadcrumb-item > span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.breadcrumb-item:hover {
  color: var(--text-primary);
  background: var(--surface-hover);
}
.breadcrumb-item.active {
  color: var(--accent-300, #F7A85B);
  font-weight: 600;
}
.breadcrumb-sep {
  color: var(--text-muted);
  opacity: 0.5;
  flex-shrink: 0;
}

/* ── 主体 ── */
.side-panel-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  padding: 0;
}
.file-list {
  flex: 1;
  min-height: 100px;
  overflow-y: auto;
  padding: 6px;
  scrollbar-width: thin;
  scrollbar-color: transparent transparent;
}
.file-list:hover {
  scrollbar-color: var(--scrollbar) transparent;
}
.file-list::-webkit-scrollbar {
  width: 4px;
}
.file-list::-webkit-scrollbar-track {
  background: transparent;
}
.file-list::-webkit-scrollbar-thumb {
  background: transparent;
  border-radius: 4px;
}
.file-list:hover::-webkit-scrollbar-thumb {
  background: var(--scrollbar);
}

.file-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  text-align: left;
  border: 0;
  border-radius: var(--radius-md, 8px);
  padding: 7px 9px;
  cursor: pointer;
  color: var(--text-primary);
  background: transparent;
  font-size: 13px;
  transition: background 0.12s ease;
}
.file-row:hover {
  background: var(--surface-hover);
}
.file-row.is-dir .file-name {
  font-weight: 500;
}
.file-icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  color: var(--text-muted);
}
.file-row.is-dir .file-icon {
  color: var(--accent-300, #F7A85B);
}
.file-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.back-row {
  color: var(--text-muted) !important;
  font-size: 12px;
}
.back-row:hover {
  color: var(--text-secondary) !important;
}

small {
  color: var(--text-muted);
  font-size: 11px;
  flex-shrink: 0;
}
.empty {
  color: var(--text-secondary);
  font-size: 12px;
  padding: 24px 18px;
  text-align: center;
}

.error {
  margin: 8px 10px;
  padding: 8px 10px;
  color: #c94b52;
  background: rgba(201, 75, 82, 0.1);
  border-radius: var(--radius-md, 8px);
  font-size: 12px;
}

/* ── 编辑器 ── */
.editor {
  height: 42%;
  min-height: 170px;
  display: flex;
  flex-direction: column;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}
.editor-header {
  min-height: 40px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  border-bottom: 1px solid var(--border);
  color: var(--text-primary);
}
.editor-filename {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 500;
}
.editor-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}
.editor textarea {
  flex: 1;
  min-height: 0;
  resize: none;
  margin: 8px;
  padding: 10px;
  background: var(--surface);
  color: var(--text-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius-md, 8px);
  font: 12px/1.5 'Cascadia Code', 'JetBrains Mono', monospace;
  outline: none;
}
.editor textarea:focus {
  border-color: var(--accent-300, #F7A85B);
}

/* ── 刷新图标旋转 ── */
.refresh-icon {
  transition: transform 0.2s ease;
}
.refresh-icon.spinning {
  animation: panel-refresh-spin 1s linear infinite;
}
@keyframes panel-refresh-spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
</style>
