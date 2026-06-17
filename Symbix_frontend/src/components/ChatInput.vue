<template>
  <div class="input-area">
    <n-input
      v-model:value="inputValue"
      type="textarea"
      :autosize="{ minRows: 1, maxRows: 4 }"
      placeholder="输入消息，Enter 发送，Shift+Enter 换行"
      @keydown.enter.exact.prevent="handleSend"
      :disabled="loading"
      class="chat-input"
      input-props="{ id: 'chat-message-input', name: 'message' }"
    />
    <n-button
      type="primary"
      circle
      @click="handleSend"
      :disabled="!inputValue.trim() || loading"
      class="send-btn"
    >
      <template #icon>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="22" y1="2" x2="11" y2="13"></line>
          <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
        </svg>
      </template>
    </n-button>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{ loading: boolean }>()
const emit = defineEmits<{ send: [text: string] }>()

const inputValue = ref('')

function handleSend() {
  const text = inputValue.value.trim()
  if (!text || props.loading) return
  emit('send', text)
  inputValue.value = ''
}
</script>

<style scoped>
.input-area {
  display: flex;
  gap: 10px;
  align-items: flex-end;
  padding: 16px 0;
  flex-shrink: 0;
}
.chat-input {
  flex: 1;
  overflow: hidden;
  border-radius: 20px;
}
.chat-input :deep(.n-input-wrapper) {
  padding: 0 !important;
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  border-radius: 20px !important;
}
.chat-input :deep(.n-input__textarea-el) {
  background: transparent !important;
  border: 1px solid #2a2a2f !important;
  border-radius: 20px !important;
  padding: 13px 16px 11px 16px;
  caret-color: #6366f1;
  color: #e0e0e0;
  transition: border-color 0.2s ease;
  line-height: 1.5;
  vertical-align: middle;
}
.chat-input :deep(.n-input__placeholder) {
  padding: 12px 16px !important;
  line-height: 1.5 !important;
  top: 0 !important;
  display: flex;
  align-items: center;
}
.chat-input :deep(.n-input__textarea-el:hover) {
  border-color: #3a3a42 !important;
}
.chat-input :deep(.n-input__textarea-el:focus) {
  border-color: #6366f1 !important;
  outline: none !important;
}
.chat-input :deep(.n-input__border),
.chat-input :deep(.n-input__state-border) {
  display: none !important;
}
.send-btn {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  background: #6366f1 !important;
  transition: all 0.2s ease;
}
.send-btn:not(:disabled):hover {
  background: #818cf8 !important;
  transform: scale(1.05);
}
.send-btn:disabled {
  background: #2a2a2f !important;
  opacity: 0.5;
}
.chat-input :deep(.n-input) {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  border-radius: 20px !important;
}
.chat-input :deep(.n-input)::before {
  display: none !important;
}
.chat-input :deep(.n-input__textarea-mirror) {
  background: transparent !important;
  border: none !important;
}
</style>
