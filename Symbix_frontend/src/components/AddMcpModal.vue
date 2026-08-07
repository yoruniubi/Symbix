<template>
  <n-modal
    :show="show"
    preset="card"
    title="添加 MCP Server"
    style="width: 480px; max-width: 94vw;"
    :bordered="false"
    class="add-modal"
    @update:show="emit('update:show', $event)"
  >
    <n-tabs :value="mode" type="segment" size="small" style="margin-bottom: 12px;" @update:value="emit('update:mode', $event)">
      <n-tab-pane name="remote" tab="远程 URL" />
      <n-tab-pane name="npm" tab="本地 npm" />
    </n-tabs>
    <n-form label-placement="top" size="small">
      <n-form-item label="Server ID" required>
        <n-input v-model:value="form.server_id" placeholder="例如 context7 / playwright" />
      </n-form-item>
      <template v-if="mode === 'remote'">
        <n-form-item label="远程 URL" required>
          <n-input v-model:value="form.url" placeholder="https://.../sse 或 /mcp" />
        </n-form-item>
        <n-form-item label="Transport">
          <n-select
            v-model:value="form.transport"
            :options="[{ label: 'SSE', value: 'sse' }, { label: 'Streamable HTTP', value: 'streamable_http' }]"
          />
        </n-form-item>
        <n-form-item label="Headers JSON（可选）">
          <n-input v-model:value="form.headersText" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" placeholder='{"Authorization":"Bearer xxx"}' />
        </n-form-item>
      </template>
      <template v-else>
        <n-form-item label="npm 包名" required>
          <n-input v-model:value="form.package_name" placeholder="例如 @playwright/mcp@latest" />
        </n-form-item>
        <n-form-item label="额外参数（空格分隔，可选）">
          <n-input v-model:value="form.argsText" placeholder="例如 --headless" />
        </n-form-item>
      </template>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="emit('update:show', false)">取消</n-button>
        <n-button type="primary" :loading="installing" @click="emit('submit')">
          {{ mode === 'remote' ? '连接' : '安装' }}
        </n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
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
