<template>
  <div class="left-panel">
    <div class="left-panel-header">
      <n-text strong style="font-size: 16px;">对话历史</n-text>
      <n-button size="small" quaternary circle @click="emit('new-chat')" title="新建对话">
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
        <!-- 展示模式 -->
        <n-ellipsis v-else style="max-width: 120px; flex: 1; min-width: 0;" :title="session.title">
          {{ session.title }}
        </n-ellipsis>

        <div class="item-actions" v-if="editingId !== session.id">
          <n-button
            text
            size="tiny"
            class="action-btn"
            @click.stop="startRename(session)"
            title="重命名"
          >
            <n-icon size="13">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
              </svg>
            </n-icon>
          </n-button>
          <n-button
            text
            size="tiny"
            class="action-btn delete-btn"
            @click.stop="emit('delete-session', session.id)"
            title="删除此对话"
          >
            <n-icon size="13">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"/>
                <line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </n-icon>
          </n-button>
        </div>
      </div>
      <n-empty v-if="sessions.length === 0" description="暂无对话" size="small" style="margin-top: 40px;" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'

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

const editingId = ref<string | null>(null)
const editTitle = ref('')
const editInputRef = ref<HTMLInputElement | null>(null)

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
  height: 100%;
  background: #18181c;
  border-right: 1px solid #2a2a2f;
  display: flex;
  flex-direction: column;
  padding: 12px 8px;
  overflow: hidden;
}
.left-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
}
.history-list {
  flex: 1;
  overflow-y: auto;
  margin-top: 4px;
}
.history-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 8px;
  border-radius: 7px;
  cursor: pointer;
  font-size: 12px;
  color: #999;
  transition: background 0.15s;
  margin-bottom: 1px;
}
.history-item:hover { background: #232328; color: #ddd; }
.history-item.active { background: #2e2e38; color: #fff; }

.item-actions {
  display: flex;
  align-items: center;
  gap: 0;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.15s ease;
}
.history-item:hover .item-actions {
  opacity: 1;
}
.action-btn {
  color: #666 !important;
  padding: 2px !important;
}
.action-btn:hover {
  color: #a0a0b8 !important;
}
.delete-btn:hover {
  color: #f87171 !important;
}

.title-input {
  flex: 1;
  min-width: 0;
  background: rgba(0, 0, 0, 0.35);
  border: 1px solid rgba(99, 102, 241, 0.5);
  border-radius: 4px;
  color: #e5e7eb;
  font-size: 12px;
  padding: 2px 6px;
  outline: none;
  width: 100%;
}
</style>