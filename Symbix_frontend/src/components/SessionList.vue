<template>
  <div class="left-panel" :style="{ width: panelWidth + 'px' }">
    <div class="left-panel-header">
      <n-text strong style="font-size: 16px;">{{ t('sessionList.title') }}</n-text>
      <n-button size="small" quaternary circle @click="emit('new-chat')" :title="t('sessionList.newChat')">
        <template #icon>
          <n-icon>
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M19 11h-6V5h-2v6H5v2h6v6h2v-6h6z"/></svg>
          </n-icon>
        </template>
      </n-button>
    </div>
    <n-divider style="margin: 8px 0;" />
    <div class="history-list">
      <div
        v-for="session in sessions"
        :key="session.id"
        class="history-item"
        :class="{ active: session.id === activeSessionId }"
        @click="onItemClick(session.id)"
      >
        <!-- 编辑模式 -->
        <input
          v-if="editingId === session.id"
          ref="editInputRef"
          v-model="editTitle"
          class="title-input"
          @click.stop
          @keydown.enter.prevent="commitRename(session.id)"
          @keydown.escape.prevent="cancelRename"
          @blur="commitRename(session.id)"
        />
        <!-- 展示模式：宽度随面板自适应 -->
        <n-ellipsis v-else class="session-title" :title="session.title">
          {{ session.title }}
        </n-ellipsis>

        <div class="item-actions" v-if="editingId !== session.id">
          <n-button
            size="small"
            quaternary
            class="panel-icon-btn"
            @click.stop="startRename(session)"
            :title="t('sessionList.rename')"
          >
            <template #icon>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
              </svg>
            </template>
          </n-button>
          <n-button
            size="small"
            quaternary
            type="error"
            class="panel-icon-btn"
            @click.stop="emit('delete-session', session.id)"
            :title="t('sessionList.delete')"
          >
            <template #icon>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                <line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/>
              </svg>
            </template>
          </n-button>
        </div>
      </div>
      <n-empty v-if="sessions.length === 0" :description="t('sessionList.empty')" size="small" style="margin-top: 40px;" />
    </div>

    <!-- VSCode 风格拖拽缩放条 -->
    <div
      class="resize-handle"
      :class="{ dragging: isResizing }"
      @mousedown.prevent="startResize"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
interface Session {
  id: string
  title: string
  messages: { role: string; content: string }[]
}

defineProps<{
  sessions: Session[]
  activeSessionId: string | null
}>()

const emit = defineEmits<{
  'new-chat': []
  'load-session': [id: string]
  'delete-session': [id: string]
  'rename-session': [id: string, newTitle: string]
}>()

const STORAGE_KEY = 'symbix-session-list-width'
const MIN_WIDTH = 140
const MAX_WIDTH = 420
const DEFAULT_WIDTH = 180

const panelWidth = ref(DEFAULT_WIDTH)
const isResizing = ref(false)
const editingId = ref<string | null>(null)
const editTitle = ref('')
const editInputRef = ref<HTMLInputElement | null>(null)

let startX = 0
let startWidth = 0

onMounted(() => {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) {
      const w = parseInt(saved, 10)
      if (!Number.isNaN(w)) {
        panelWidth.value = clamp(w, MIN_WIDTH, MAX_WIDTH)
      }
    }
  } catch { /* ignore */ }
})

function clamp(v: number, min: number, max: number) {
  return Math.min(max, Math.max(min, v))
}

function startResize(e: MouseEvent) {
  isResizing.value = true
  startX = e.clientX
  startWidth = panelWidth.value
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  window.addEventListener('mousemove', onResize)
  window.addEventListener('mouseup', stopResize)
}

function onResize(e: MouseEvent) {
  if (!isResizing.value) return
  const delta = e.clientX - startX
  panelWidth.value = clamp(startWidth + delta, MIN_WIDTH, MAX_WIDTH)
}

function stopResize() {
  if (!isResizing.value) return
  isResizing.value = false
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  window.removeEventListener('mousemove', onResize)
  window.removeEventListener('mouseup', stopResize)
  try {
    localStorage.setItem(STORAGE_KEY, String(panelWidth.value))
  } catch { /* ignore */ }
}

onBeforeUnmount(() => {
  window.removeEventListener('mousemove', onResize)
  window.removeEventListener('mouseup', stopResize)
})

function onItemClick(id: string) {
  if (editingId.value) return
  emit('load-session', id)
}

function startRename(session: Session) {
  editingId.value = session.id
  editTitle.value = session.title
  nextTick(() => {
    const el = editInputRef.value
    if (el) {
      el.focus()
      el.select()
    }
  })
}

function commitRename(id: string) {
  if (editingId.value !== id) return
  const trimmed = editTitle.value.trim()
  editingId.value = null
  if (!trimmed) return
  emit('rename-session', id, trimmed)
}

function cancelRename() {
  editingId.value = null
  editTitle.value = ''
}
</script>

<style scoped>
.left-panel {
  position: relative;
  z-index: 1;
  width: 180px;
  min-width: 140px;
  max-width: 420px;
  height: 100%;
  background: var(--bg-surface);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 12px 8px;
  overflow: hidden;
  flex-shrink: 0;
  box-sizing: border-box;
}
.left-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  color: var(--text-primary);
}
.history-list {
  flex: 1;
  overflow-y: auto;
  margin-top: 4px;
  scrollbar-width: none;
  -ms-overflow-style: none;
}
.history-list::-webkit-scrollbar {
  width: 0;
  height: 0;
  display: none;
}
.history-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 8px;
  border-radius: var(--radius-sm, 6px);
  cursor: pointer;
  font-size: 12px;
  color: var(--text-secondary);
  transition: background var(--duration-fast, 120ms) var(--ease-standard, ease),
              color var(--duration-fast, 120ms) var(--ease-standard, ease);
  margin-bottom: 1px;
}
.history-item:hover {
  background: var(--surface-hover);
  color: var(--text-primary);
}
.history-item.active {
  background: var(--accent-soft);
  color: var(--text-primary);
}

.session-title {
  flex: 1;
  min-width: 0;
}

.item-actions {
  display: flex;
  align-items: center;
  gap: 0;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity var(--duration-fast, 120ms) ease;
  margin-left: auto
}
.history-item:hover .item-actions {
  opacity: 1;
}

.title-input {
  flex: 1;
  min-width: 0;
  background: var(--bg-elevated);
  border: 1px solid var(--accent-border);
  border-radius: var(--radius-sm, 6px);
  color: var(--text-primary);
  font-size: 12px;
  padding: 2px 6px;
  outline: none;
  width: 100%;
}

.resize-handle {
  position: absolute;
  top: 0;
  right: -3px;
  width: 6px;
  height: 100%;
  cursor: col-resize;
  z-index: 30;
  background: transparent;
  transition: background var(--duration-fast, 120ms) ease;
}
.resize-handle:hover,
.resize-handle.dragging {
  background: var(--accent-border);
}
</style>