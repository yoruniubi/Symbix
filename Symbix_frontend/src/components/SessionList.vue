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
        <n-ellipsis style="max-width: 160px;">{{ session.title }}</n-ellipsis>
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
}>()
</script>

<style scoped>
.left-panel {
  width: 220px;
  min-width: 180px;
  background: #18181c;
  border-right: 1px solid #2a2a2f;
  display: flex;
  flex-direction: column;
  padding: 16px 12px;
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
.left-panel-footer { flex-shrink: 0; }
</style>
