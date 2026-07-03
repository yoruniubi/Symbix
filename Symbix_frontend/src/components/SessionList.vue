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
        v-for="(session, idx) in sessions"
        :key="idx"
        class="history-item"
        :class="{ active: idx === activeSession }"
        @click="emit('load-session', idx)"
      >
        <n-ellipsis style="max-width: 140px; flex: 1; min-width: 0;">{{ session.title }}</n-ellipsis>
        <n-button
          text
          size="tiny"
          class="delete-btn"
          @click.stop="emit('delete-session', idx)"
          title="删除此对话"
        >
          <n-icon size="14">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </n-icon>
        </n-button>
      </div>
      <n-empty v-if="sessions.length === 0" description="暂无对话" size="small" style="margin-top: 40px;" />
    </div>
  </div>
</template>

<script setup lang="ts">
interface Session {
  title: string
  messages: { role: string; content: string }[]
}

defineProps<{
  sessions: Session[]
  activeSession: number
}>()

const emit = defineEmits<{
  'new-chat': []
  'load-session': [idx: number]
  'delete-session': [idx: number]
}>()
</script>

<style scoped>
.left-panel {
  position: relative;
  z-index: 1;
  width: 220px;
  min-width: 180px;
  height: 100%;
  background: #18181c;
  border-right: 1px solid #2a2a2f;
  display: flex;
  flex-direction: column;
  padding: 16px 12px;
  overflow: hidden;
}
.left-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
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
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  color: #aaa;
  transition: background 0.15s;
  margin-bottom: 2px;
}
.history-item:hover { background: #232328; color: #fff; }
.history-item.active { background: #2e2e38; color: #fff; }
.delete-btn {
  opacity: 0;
  color: #666 !important;
  flex-shrink: 0;
  transition: all 0.15s ease;
  padding: 2px !important;
  left:40px;
}
.history-item:hover .delete-btn {
  opacity: 1;
}
.delete-btn:hover {
  color: #f87171 !important;
}
</style>