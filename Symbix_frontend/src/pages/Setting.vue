<template>
  <div class="setting-page">
    <TitleBar />
    <n-card title="设置" style="max-width: 520px; margin: 60px auto;">
      <n-form :model="form" label-placement="top">
        <n-form-item label="API Key">
          <n-input
            v-model:value="form.apiKey"
            type="password"
            show-password-on="click"
            placeholder="输入你的 API Key"
          />
        </n-form-item>
        <n-form-item label="Base URL">
          <n-input
            v-model:value="form.baseUrl"
            placeholder="例如 https://api.openai.com（自动补全 /v1）"
          />
        </n-form-item>
        <n-form-item label="模型选择">
          <n-input-group>
            <n-select
              v-model:value="form.model"
              :options="modelOptions"
              :loading="fetchingModels"
              filterable
              tag
              placeholder="点击「获取模型」或手动输入"
              style="flex: 1"
            />
            <n-button :loading="fetchingModels" @click="handleFetchModels" style="width: 110px; flex-shrink: 0;">
              {{ fetchingModels ? '获取中...' : '获取模型' }}
            </n-button>
          </n-input-group>
        </n-form-item>
        <n-space justify="end" style="margin-top: 8px;">
          <n-button @click="handleReset">重置</n-button>
          <n-button :loading="testing" @click="handleTest">测试连接</n-button>
          <n-button type="primary" @click="handleSave">保存</n-button>
        </n-space>
      </n-form>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import TitleBar from '@/components/TitleBar.vue'
import { useSettings } from '@/composables/useSettings'
import { useApiClient } from '@/composables/useApiClient'

const router = useRouter()
const message = useMessage()
const { settings, loadSettings, saveSettings, resetSettings } = useSettings()
const { fetchModels, testConnection } = useApiClient()

const form = ref({ apiKey: '', baseUrl: '', model: '' })
const modelOptions = ref<{ label: string; value: string }[]>([])
const fetchingModels = ref(false)
const testing = ref(false)

onMounted(() => {
  loadSettings()
  form.value = {
    apiKey: settings.value.apiKey,
    baseUrl: settings.value.baseUrl,
    model: settings.value.model,
  }
  if (settings.value.model) {
    modelOptions.value = [{ label: settings.value.model, value: settings.value.model }]
  }
})

async function handleFetchModels() {
  if (!form.value.apiKey || !form.value.baseUrl) {
    message.warning('请先填写 API Key 和 Base URL')
    return
  }
  fetchingModels.value = true
  try {
    const models = await fetchModels(form.value.apiKey, form.value.baseUrl)
    modelOptions.value = models.map(id => ({ label: id, value: id }))
    if (models.length > 0) {
      message.success(`获取到 ${models.length} 个模型`)
      if (!form.value.model) form.value.model = models[0]
    } else {
      message.warning('未获取到模型列表')
    }
  } catch (e: any) {
    message.error(`获取失败：${e.message}`)
  } finally {
    fetchingModels.value = false
  }
}

async function handleTest() {
  if (!form.value.apiKey || !form.value.baseUrl) {
    message.warning('请先填写 API Key 和 Base URL')
    return
  }
  testing.value = true
  try {
    await testConnection(form.value.apiKey, form.value.baseUrl)
    message.success('连接成功！API Key 和 Base URL 有效')
  } catch (e: any) {
    message.error(`连接失败：${e.message}`)
  } finally {
    testing.value = false
  }
}

function handleSave() {
  saveSettings(form.value)
  message.success('设置已保存')
}

function handleReset() {
  resetSettings()
  form.value = { apiKey: '', baseUrl: '', model: '' }
  modelOptions.value = []
  message.info('已重置')
}
</script>

<style scoped>
.setting-page {
  height: 100vh;
  background-color: rgba(16, 16, 20, 0.95);
  padding-top: 32px;
  color: white;
}
</style>
