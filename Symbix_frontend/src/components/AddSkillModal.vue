<template>
  <n-modal
    :show="show"
    preset="card"
    :title="$t('addSkillModal.title')"
    style="width: 480px; max-width: 94vw;"
    :bordered="false"
    class="add-modal"
    @update:show="emit('update:show', $event)"
  >
    <n-tabs :value="mode" type="segment" size="small" style="margin-bottom: 12px;" @update:value="emit('update:mode', $event)">
      <n-tab-pane name="github" :tab="$t('addSkillModal.tabGithub')" />
      <n-tab-pane name="custom" :tab="$t('addSkillModal.tabCustom')" />
    </n-tabs>
    <n-form label-placement="top" size="small">
      <template v-if="mode === 'github'">
        <n-form-item :label="$t('addSkillModal.repoLabel')" required>
          <n-input v-model:value="form.repo_url" :placeholder="$t('addSkillModal.repoPlaceholder')" />
        </n-form-item>
        <n-form-item :label="$t('addSkillModal.skillNameLabel')">
          <n-input v-model:value="form.skill_name" :placeholder="$t('addSkillModal.skillNamePlaceholder')" />
        </n-form-item>
        <n-form-item :label="$t('addSkillModal.branchLabel')">
          <n-input v-model:value="form.branch" :placeholder="$t('addSkillModal.branchPlaceholder')" />
        </n-form-item>
        <n-form-item :label="$t('addSkillModal.overwriteLabel')">
          <n-switch v-model:value="form.overwrite" />
        </n-form-item>
      </template>
      <template v-else>
        <n-form-item :label="$t('addSkillModal.customNameLabel')" required>
          <n-input v-model:value="form.skill_name" :placeholder="$t('addSkillModal.customNamePlaceholder')" />
        </n-form-item>
        <n-form-item :label="$t('addSkillModal.displayNameLabel')">
          <n-input v-model:value="form.display_name" :placeholder="$t('addSkillModal.displayNamePlaceholder')" />
        </n-form-item>
        <n-form-item :label="$t('addSkillModal.descLabel')">
          <n-input v-model:value="form.description" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" :placeholder="$t('addSkillModal.descPlaceholder')" />
        </n-form-item>
        <n-form-item :label="$t('addSkillModal.purposeLabel')">
          <n-input v-model:value="form.purpose" type="textarea" :autosize="{ minRows: 2, maxRows: 3 }" />
        </n-form-item>
        <n-form-item :label="$t('addSkillModal.instructionsLabel')">
          <n-input v-model:value="form.instructions" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" />
        </n-form-item>
      </template>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="emit('update:show', false)">{{ $t('addSkillModal.cancel') }}</n-button>
        <n-button type="primary" :loading="creating" @click="emit('submit')">
          {{ mode === 'github' ? $t('addSkillModal.install') : $t('addSkillModal.create') }}
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
