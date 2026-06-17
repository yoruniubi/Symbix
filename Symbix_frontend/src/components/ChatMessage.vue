<template>
  <div class="message-row" :class="msg.role">
    <div class="message-bubble" :class="msg.role">
      <n-text style="white-space: pre-wrap;">{{ msg.content }}</n-text>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  msg: { role: 'user' | 'assistant'; content: string }
}>()
</script>

<style scoped>
.message-row {
  display: flex;
  margin: 12px 0;
}

.message-row.user {
  justify-content: flex-end;
}

.message-row.assistant {
  justify-content: flex-start;
}

.message-bubble {
  max-width: min(75%, 800px);
  padding: 12px 16px;
  border-radius: 16px;
  color: #e5e7eb;
  word-break: break-word;
  overflow-wrap: anywhere;
  line-height: 1.6;
}

.message-bubble.user {
  background: linear-gradient(135deg, #6366f1, #4f46e5);
  border-bottom-right-radius: 4px;
}

.message-bubble.assistant {
  background: #2a2d35;
  border-bottom-left-radius: 4px;
}
</style>
