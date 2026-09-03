<template>
  <n-modal
    :show="show"
    preset="card"
    :title="t('addMcpModal.title')"
    style="width: 480px; max-width: 94vw;"
    :bordered="false"
    class="add-modal"
    @update:show="emit('update:show', $event)"
  >
    <n-tabs :value="mode" type="segment" size="small" style="margin-bottom: 12px;" @update:value="emit('update:mode', $event)">
      <n-tab-pane name="raw" :tab="t('addMcpModal.tabRaw')" />
      <n-tab-pane name="remote" :tab="t('addMcpModal.tabRemote')" />
    </n-tabs>
    <n-form label-placement="top" size="small">
      <template v-if="mode === 'raw'">
        <n-form-item :label="t('addMcpModal.rawJsonLabel')">
          <n-input
            v-model:value="form.rawJson"
            type="textarea"
            :autosize="{ minRows: 6, maxRows: 16 }"
            :placeholder="t('addMcpModal.rawJsonPlaceholder')"
            spellcheck="false"
          />
        </n-form-item>
        <p class="add-modal-hint">{{ t('addMcpModal.rawJsonHint') }}</p>
      </template>
      <template v-else-if="mode === 'remote'">
        <n-form-item :label="t('addMcpModal.serverIdLabel')" required>
          <n-input v-model:value="form.server_id" :placeholder="t('addMcpModal.serverIdPlaceholder')" />
        </n-form-item>
        <n-form-item :label="t('addMcpModal.remoteUrlLabel')" required>
          <n-input v-model:value="form.url" :placeholder="t('addMcpModal.remoteUrlPlaceholder')" />
        </n-form-item>
        <n-form-item :label="t('addMcpModal.transportLabel')">
          <n-select
            v-model:value="form.transport"
            :options="[ { label: 'Streamable HTTP', value: 'streamable_http' },{ label: 'SSE', value: 'sse' }]"
          />
        </n-form-item>
        <p class="add-modal-hint" style="margin-top:-8px;">{{ t('addMcpModal.transportHint') }}</p>
        <n-form-item :label="t('addMcpModal.apiKeyLabel')">
          <n-input
            v-model:value="form.apiKey"
            type="password"
            show-password-on="click"
            :placeholder="t('addMcpModal.apiKeyPlaceholder')"
          />
        </n-form-item>
        <p class="add-modal-hint" style="margin-top:-8px;">
          {{ t('addMcpModal.apiKeyHint') }}
        </p>
        <n-form-item :label="t('addMcpModal.headersLabel')">
          <n-input v-model:value="form.headersText" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" :placeholder="t('addMcpModal.headersPlaceholder')" />
        </n-form-item>
        <p class="add-modal-hint" style="margin-top:-8px;">{{ t('addMcpModal.oauthHint') }}</p>
      </template>
    </n-form>
    <n-alert v-if="oauthWaiting" type="info" :show-icon="false" style="margin-top: 12px;">
      {{ t('addMcpModal.oauthPending') }}
    </n-alert>
    <template #footer>
      <n-space justify="end">
        <n-button @click="emit('update:show', false)">{{ t('addMcpModal.cancel') }}</n-button>
        <n-button type="primary" :loading="installing" @click="emit('submit')">
          {{ mode === 'remote' ? t('addMcpModal.connect') : t('addMcpModal.add') }}
        </n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

defineProps<{
  show: boolean
  installing: boolean
  oauthWaiting?: boolean
  mode: 'remote' | 'raw'
  form: {
    server_id: string
    package_name: string
    argsText: string
    url: string
    transport: string
    apiKey: string
    headersText: string
    rawJson: string
  }
}>()

const emit = defineEmits<{
  (e: 'update:show', value: boolean): void
  (e: 'update:mode', value: 'raw' | 'remote'): void
  (e: 'submit'): void
}>()
</script>

<style scoped>
.add-modal-hint {
  margin: -4px 0 0;
  font-size: 11.5px;
  line-height: 1.55;
  opacity: 0.68;
}
.add-modal-hint code {
  padding: 1px 4px;
  border-radius: 4px;
  background: rgba(127,127,127,0.18);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
</style>
