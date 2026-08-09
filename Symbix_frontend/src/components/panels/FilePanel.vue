<template>
  <transition name="panel-slide">
    <div v-if="activePanel === 'files'" class="side-panel" :class="{ 'is-resizing': isResizing }" :style="{ width: `${panelWidth}px` }">
      <div class="panel-resize-handle" title="拖动调整面板宽度" @mousedown="startResize" />
      <div class="side-panel-header">
        <span class="side-panel-title">{{ $t('filePanel.title') }}</span>
        <div class="side-panel-actions">
          <button type="button" class="panel-action-btn" :title="$t('filePanel.openDir')" @click="chooseDirectory">{{ $t('filePanel.openDir') }}</button>
          <button type="button" class="panel-icon-btn" :title="$t('filePanel.refresh')" @click="loadDirectory(currentPath)">↻</button>
          <button type="button" class="panel-icon-btn close-btn" :title="$t('filePanel.close')" @click="emit('update:activePanel', null)">×</button>
        </div>
      </div>

      <div class="breadcrumb">
        <button type="button" @click="loadDirectory('.')">{{ $t('filePanel.project') }}</button>
        <template v-if="isExternalPath">
          <span>/</span>
          <button type="button" @click="loadDirectory(externalRoot)">{{ externalRootName }}</button>
        </template>
        <template v-for="(part, index) in breadcrumbParts" :key="`${part}-${index}`">
          <span>/</span>
          <button type="button" @click="loadBreadcrumb(index)">
            {{ part }}
          </button>
        </template>
      </div>

      <div v-if="error" class="error">{{ error }}</div>
      <div v-if="loading" class="empty">{{ $t('filePanel.loading') }}</div>

      <div v-else class="file-list">
        <button
          v-if="currentPath !== '.'"
          type="button"
          class="file-row"
          @click="loadDirectory(parentPath)"
        >
          <span>↩</span><span>{{ $t('filePanel.backParent') }}</span>
        </button>

        <button
          v-for="entry in entries"
          :key="entry.path"
          type="button"
          class="file-row"
          @click="openEntry(entry)"
        >
          <span>{{ entry.type === 'directory' ? '▸' : '·' }}</span>
          <span class="file-name">{{ entry.name }}</span>
          <small v-if="entry.type === 'file'">{{ formatSize(entry.size) }}</small>
        </button>

        <div v-if="entries.length === 0" class="empty">{{ $t('filePanel.empty') }}</div>
      </div>

      <div v-if="selectedFile" class="editor">
        <div class="editor-header">
          <span>{{ selectedFile.name }}</span>
          <button type="button" @click="saveFile">{{ $t('filePanel.save') }}</button>
          <button type="button" @click="deleteFile">{{ $t('filePanel.delete') }}</button>
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
  inset: 0 auto 0 0;
  min-width: var(--panel-min-width);
  max-width: min(var(--panel-max-width), 70vw);
  background: var(--panel-bg);
  backdrop-filter: blur(16px);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  z-index: 5;
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

.editor-header {
  min-height: 46px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 10px;
  border-bottom: 1px solid var(--border);
  color: var(--text-primary);
}

.side-panel-header {
  min-height: 46px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 0 12px 0 16px;
  border-bottom: 1px solid var(--border);
  flex: 0 0 auto;
}

.side-panel-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.side-panel-actions {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-shrink: 0;
}

.panel-header strong,
.editor-header span {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

button {
  border: 0;
  border-radius: 5px;
  padding: 5px 7px;
  cursor: pointer;
  color: var(--text-secondary);
  background: transparent;
}

button:hover {
  color: var(--text-primary);
  background: var(--surface-hover);
}

.panel-action-btn {
  font-size: 12px;
  white-space: nowrap;
}

.panel-icon-btn {
  width: 28px;
  height: 28px;
  padding: 0;
  font-size: 16px;
  line-height: 1;
}

.close-btn {
  color: var(--text-muted) !important;
}

.close-btn:hover {
  color: var(--text-secondary) !important;
  background: var(--surface-hover) !important;
}

.breadcrumb {
  display: flex;
  gap: 3px;
  padding: 7px 9px;
  overflow: auto;
  white-space: nowrap;
  border-bottom: 1px solid var(--border);
  font-size: 12px;
}

.file-list {
  flex: 1;
  min-height: 100px;
  overflow: auto;
  padding: 5px;
}

.file-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 7px;
  text-align: left;
  color: var(--text-primary);
}

.file-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

small,
.empty {
  color: var(--text-secondary);
  font-size: 12px;
}

.empty {
  padding: 18px;
  text-align: center;
}

.error {
  margin: 7px;
  padding: 7px;
  color: #c94b52;
  background: rgba(201, 75, 82, 0.1);
  border-radius: 5px;
  font-size: 12px;
}

.editor {
  height: 42%;
  min-height: 170px;
  display: flex;
  flex-direction: column;
  border-top: 1px solid var(--border);
}

.editor textarea {
  flex: 1;
  min-height: 0;
  resize: none;
  margin: 7px;
  padding: 8px;
  background: var(--surface);
  color: var(--text-primary);
  border: 1px solid var(--border);
  border-radius: 5px;
  font: 12px/1.5 monospace;
}
</style>