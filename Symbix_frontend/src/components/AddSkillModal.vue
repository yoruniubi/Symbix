<template>
  <n-modal
    :show="show"
    preset="card"
    title="添加 Skill"
    style="width: 480px; max-width: 94vw;"
    :bordered="false"
    class="add-modal"
    @update:show="emit('update:show', $event)"
  >
    <n-tabs :value="mode" type="segment" size="small" style="margin-bottom: 12px;" @update:value="emit('update:mode', $event)">
      <n-tab-pane name="github" tab="从 GitHub 安装" />
      <n-tab-pane name="custom" tab="自定义创建" />
    </n-tabs>
    <n-form label-placement="top" size="small">
      <template v-if="mode === 'github'">
        <n-form-item label="GitHub 仓库" required>
          <n-input v-model:value="form.repo_url" placeholder="owner/repo 或 https://github.com/owner/repo" />
        </n-form-item>
        <n-form-item label="Skill 名称（可选，仓库有多个时指定）">
          <n-input v-model:value="form.skill_name" placeholder="例如 my-helper" />
        </n-form-item>
        <n-form-item label="分支（可选）">
          <n-input v-model:value="form.branch" placeholder="默认 main/master" />
        </n-form-item>
        <n-form-item label="覆盖已存在">
          <n-switch v-model:value="form.overwrite" />
        </n-form-item>
      </template>
      <template v-else>
        <n-form-item label="Skill 名称（小写、连字符）" required>
          <n-input v-model:value="form.skill_name" placeholder="例如 my-helper" />
        </n-form-item>
        <n-form-item label="显示名称">
          <n-input v-model:value="form.display_name" placeholder="例如 我的助手" />
        </n-form-item>
        <n-form-item label="描述">
          <n-input v-model:value="form.description" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" placeholder="简要说明用途" />
        </n-form-item>
        <n-form-item label="用途（可选）">
          <n-input v-model:value="form.purpose" type="textarea" :autosize="{ minRows: 2, maxRows: 3 }" />
        </n-form-item>
        <n-form-item label="指令（可选）">
          <n-input v-model:value="form.instructions" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" />
        </n-form-item>
      </template>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="emit('update:show', false)">取消</n-button>
        <n-button type="primary" :loading="creating" @click="emit('submit')">
          {{ mode === 'github' ? '安装' : '创建' }}
        </n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
defineProps<{
  show: boolean
  creating: boolean
  mode: 'github' | 'custom'
  form: {
    skill_name: string
    display_name: string
    description: string
    purpose: string
    instructions: string
    repo_url: string
    branch: string
    overwrite: boolean
  }
}>()

const emit = defineEmits<{
  (e: 'update:show', value: boolean): void
  (e: 'update:mode', value: 'github' | 'custom'): void
  (e: 'submit'): void
}>()
</script>
