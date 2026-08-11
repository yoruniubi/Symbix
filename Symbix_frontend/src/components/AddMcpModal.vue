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
      <n-tab-pane name="remote" :tab="t('addMcpModal.tabRemote')" />
      <n-tab-pane name="npm" :tab="t('addMcpModal.tabNpm')" />
    </n-tabs>
    <n-form label-placement="top" size="small">
      <n-form-item :label="t('addMcpModal.serverIdLabel')" required>
        <n-input v-model:value="form.server_id" :placeholder="t('addMcpModal.serverIdPlaceholder')" />
      </n-form-item>
      <template v-if="mode === 'remote'">
        <n-form-item :label="t('addMcpModal.remoteUrlLabel')" required>
          <n-input v-model:value="form.url" :placeholder="t('addMcpModal.remoteUrlPlaceholder')" />
        </n-form-item>
        <n-form-item :label="t('addMcpModal.transportLabel')">
          <n-select
            v-model:value="form.transport"
            :options="[{ label: 'SSE', value: 'sse' }, { label: 'Streamable HTTP', value: 'streamable_http' }]"
          />
        </n-form-item>
        <n-form-item :label="t('addMcpModal.headersLabel')">
          <n-input v-model:value="form.headersText" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" :placeholder="t('addMcpModal.headersPlaceholder')" />
        </n-form-item>
      </template>
      <template v-else>
        <n-form-item :label="t('addMcpModal.npmPackageLabel')" required>
          <n-input v-model:value="form.package_name" :placeholder="t('addMcpModal.npmPackagePlaceholder')" />
        </n-form-item>
        <n-form-item :label="t('addMcpModal.argsLabel')">
          <n-input v-model:value="form.argsText" :placeholder="t('addMcpModal.argsPlaceholder')" />
        </n-form-item>
      </template>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="emit('update:show', false)">{{ t('addMcpModal.cancel') }}</n-button>
        <n-button type="primary" :loading="installing" @click="emit('submit')">
          {{ mode === 'remote' ? t('addMcpModal.connect') : t('addMcpModal.install') }}
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
  mode: 'remote' | 'npm'
  form: {
    server_id: string
    package_name: string
    argsText: string
    url: string
    transport: string
    headersText: string
  }
}>()

const emit = defineEmits<{
  (e: 'update:show', value: boolean): void
  (e: 'update:mode', value: 'remote' | 'npm'): void
  (e: 'submit'): void
}>()
</script>
