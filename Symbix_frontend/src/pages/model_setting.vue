<template>
  <div class="setting-page">
    <TitleBar />
    <div class="setting-card-wrapper">
      <n-card title="模型设置" class="setting-card">
        <template #header-extra>
          <n-button circle text @click="router.back()">
            <template #icon>
              <span style="font-size: 18px; font-weight: bold;">✕</span>
            </template>
          </n-button>
        </template>

        <div class="scrollable-form">
          <n-form :model="form" label-placement="top">

            <!-- 厂商选择 -->
            <n-form-item label="模型厂商">
              <div class="provider-grid">
                <div
                  v-for="p in providers"
                  :key="p.id"
                  class="provider-card"
                  :class="{ active: selectedProvider === p.id }"
                  @click="selectProvider(p)"
                >
                  <span class="provider-icon">{{ p.icon }}</span>
                  <span class="provider-name">{{ p.name }}</span>
                </div>
              </div>
            </n-form-item>

            <!-- API Key -->
            <n-form-item label="API Key">
              <n-input
                v-model:value="form.apiKey"
                type="password"
                show-password-on="click"
                placeholder="输入你的 API Key"
              />
            </n-form-item>

            <!-- Base URL：仅自定义或需要中转时显示 -->
            <n-form-item label="Base URL" v-if="selectedProvider === 'custom' || currentProviderNeedsBase">
              <n-input
                v-model:value="form.baseUrl"
                :placeholder="selectedProvider === 'custom' ? '例如 https://your-proxy.com/v1' : '可选，留空使用官方地址'"
              />
            </n-form-item>

            <!-- 模型选择 -->
            <n-form-item label="模型">
              <n-input-group>
                <n-select
                  v-model:value="form.model"
                  :options="modelOptions"
                  :loading="fetchingModels"
                  filterable
                  tag
                  placeholder="选择预设模型或手动输入"
                  style="flex: 1"
                />
                <n-button
                  v-if="selectedProvider === 'custom'"
                  :loading="fetchingModels"
                  @click="handleFetchModels"
                  style="width: 110px; flex-shrink: 0;"
                >
                  {{ fetchingModels ? '获取中...' : '获取模型' }}
                </n-button>
              </n-input-group>
            </n-form-item>
             <div v-if="form.model" style="margin-top: 6px; font-size: 11px; color: #6b6b80;">
                litellm 调用标识：<span style="color: #818cf8;">{{ form.model }}</span>
              </div>

            <!-- 系统提示词 -->
            <n-form-item label="系统提示词">
              <n-input
                v-model:value="form.systemPrompt"
                type="textarea"
                :autosize="{ minRows: 3, maxRows: 8 }"
                placeholder="设置 AI 的系统提示词，用于定义 AI 的角色、行为或回答风格..."
              />
              <template #extra>
                <div class="preset-tags">
                  <n-tag
                    v-for="preset in systemPromptPresets"
                    :key="preset.label"
                    size="small"
                    :type="form.systemPrompt === preset.text ? 'primary' : 'default'"
                    :bordered="false"
                    style="cursor: pointer; margin-right: 6px; margin-bottom: 4px;"
                    @click="applySystemPromptPreset(preset)"
                  >
                    {{ preset.label }}
                  </n-tag>
                </div>
              </template>
            </n-form-item>

            <n-space justify="end" style="margin-top: 8px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.06);">
              <n-button @click="handleReset">重置</n-button>
              <n-button :loading="testing" @click="handleTest">测试连接</n-button>
              <n-button type="primary" @click="handleSave">保存</n-button>
            </n-space>
          </n-form>
        </div>
      </n-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import TitleBar from '@/components/TitleBar.vue'
import { useSettings } from '@/composables/useSettings'
import { useApiClient } from '@/composables/useApiClient'

const router = useRouter()
const message = useMessage()
const { settings, loadSettings, saveSettings, resetSettings } = useSettings()
const { fetchModels, testConnection } = useApiClient()

interface Provider {
  id: string
  name: string
  icon: string
  baseUrl: string        // 官方地址，空字符串表示 litellm 自动处理
  needsBase: boolean     // 是否需要显示 baseUrl 输入框
  models: string[]       // litellm 格式的 model string
}

const providers: Provider[] = [
  {
    id: 'openai',
    name: 'OpenAI',
    icon: '🤖',
    baseUrl: '',
    needsBase: false,
    models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'o1', 'o3-mini'],
  },
  {
    id: 'anthropic',
    name: 'Anthropic',
    icon: '🧠',
    baseUrl: '',
    needsBase: false,
    models: [
      'anthropic/claude-opus-4-5',
      'anthropic/claude-sonnet-4-5',
      'anthropic/claude-haiku-4-5',
    ],
  },
  {
    id: 'google',
    name: 'Google',
    icon: '✨',
    baseUrl: '',
    needsBase: false,
    models: [
      'gemini/gemini-2.5-pro',
      'gemini/gemini-2.5-flash',
      'gemini/gemini-2.0-flash',
    ],
  },
  {
    id: 'deepseek',
    name: 'DeepSeek',
    icon: '🐋',
    baseUrl: 'https://api.deepseek.com/v1',
    needsBase: false,
    models: ['openai/deepseek-chat', 'openai/deepseek-reasoner'],
  },
  {
    id: 'groq',
    name: 'Groq',
    icon: '⚡',
    baseUrl: '',
    needsBase: false,
    models: [
      'groq/llama-3.3-70b-versatile',
      'groq/llama-3.1-8b-instant',
      'groq/mixtral-8x7b-32768',
    ],
  },
  {
    id: 'mistral',
    name: 'Mistral',
    icon: '🌬️',
    baseUrl: '',
    needsBase: false,
    models: [
      'mistral/mistral-large-latest',
      'mistral/mistral-small-latest',
      'mistral/codestral-latest',
    ],
  },
  {
    id: 'custom',
    name: '自定义',
    icon: '🔧',
    baseUrl: '',
    needsBase: true,
    models: [],
  },
]
const customBaseUrl = ref('')
const customModel = ref('')
const selectedProvider = ref<string>('custom')
const form = ref({ apiKey: '', baseUrl: '', model: '', systemPrompt: '' })
const modelOptions = ref<{ label: string; value: string }[]>([])
const fetchingModels = ref(false)
const testing = ref(false)

const currentProviderNeedsBase = computed(() => {
  const p = providers.find(p => p.id === selectedProvider.value)
  return p?.needsBase ?? false
})

// 系统提示词预设
const systemPromptPresets = [
  { label: '通用助手', text: '你是一个有帮助的 AI 助手，请用中文回答用户的问题。回答应准确、简洁、友好。' },
  { label: '代码专家', text: '你是一位资深软件工程师。请用中文提供清晰、可运行的代码示例，并解释关键设计决策。优先考虑最佳实践和安全性。' },
  { label: '翻译官', text: '你是一个专业的翻译助手。请将用户输入的内容翻译成中文，保持原文的语气和风格。如果是中文则翻译成英文。' },
  { label: '写作助手', text: '你是一个专业的写作助手。请帮助用户改进文章的语法、结构和表达，使其更加流畅和专业。' },
  { label: '数据分析师', text: '你是一个数据分析专家。请帮助用户解读数据、提供分析思路，并用清晰的方式呈现分析结果。' },
  { label: '创意伙伴', text: '你是一个富有创意的头脑风暴伙伴。请提供新颖的想法和独特的视角，激发用户的灵感。' },
]

function applySystemPromptPreset(preset: { label: string; text: string }) {
  if (form.value.systemPrompt === preset.text) {
    form.value.systemPrompt = ''
  } else {
    form.value.systemPrompt = preset.text
  }
}

onMounted(() => {
  loadSettings()
  form.value = {
    apiKey: settings.value.apiKey || '',
    baseUrl: settings.value.baseUrl || '',
    model: settings.value.model || '',
    systemPrompt: settings.value.systemPrompt || '',
  }

  const model = settings.value.model || ''
  const baseUrl = settings.value.baseUrl || ''
  customBaseUrl.value = settings.value.baseUrl || ''
  customModel.value = settings.value.model || ''
  // 如果有 baseUrl 说明是自定义
  if (baseUrl) {
    selectedProvider.value = 'custom'
    modelOptions.value = model ? [{ label: model, value: model }] : []
    return
  }

  // 没有 baseUrl 则按模型前缀匹配厂商
  const matched = providers.find(p =>
    p.id !== 'custom' && p.models.some(m => m === model)
  )
  if (matched) {
    selectedProvider.value = matched.id
    modelOptions.value = matched.models.map(m => ({ label: m, value: m }))
  } else {
    selectedProvider.value = 'custom'
    modelOptions.value = model ? [{ label: model, value: model }] : []
  }
})

function selectProvider(p: Provider) {
  // 离开自定义时，先保存当前填的内容
  if (selectedProvider.value === 'custom') {
    customBaseUrl.value = form.value.baseUrl
    customModel.value = form.value.model
  }

  selectedProvider.value = p.id

  if (p.id === 'custom') {
    // 切回自定义时，恢复之前保存的内容
    form.value.baseUrl = customBaseUrl.value
    form.value.model = customModel.value
    modelOptions.value = customModel.value
      ? [{ label: customModel.value, value: customModel.value }]
      : []
  } else {
    form.value.baseUrl = p.baseUrl
    modelOptions.value = p.models.map(m => ({ label: m, value: m }))
    form.value.model = p.models[0] || ''
  }
}

async function handleFetchModels() {
  if (!form.value.apiKey || !form.value.baseUrl) {
    message.warning('请先填写 API Key 和 Base URL')
    return
  }
  fetchingModels.value = true
  try {
    const models = await fetchModels(form.value.apiKey, form.value.baseUrl)
    // 自定义接口的模型统一加 openai/ 前缀
    modelOptions.value = models.map(id => ({
      label: id,
      value: id,
    }))
    if (models.length > 0) {
      message.success(`获取到 ${models.length} 个模型`)
      if (!form.value.model) {
        form.value.model = models[0]
        customModel.value = models[0]
      }
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
  if (!form.value.apiKey) {
    message.warning('请先填写 API Key')
    return
  }
  testing.value = true
  try {
    await testConnection(form.value.apiKey, form.value.baseUrl)
    message.success('连接成功！')
  } catch (e: any) {
    message.error(`连接失败：${e.message}`)
  } finally {
    testing.value = false
  }
}

function handleSave() {
  saveSettings(form.value)
  message.success('设置已保存')
  setTimeout(() => router.back(), 300)  
}

function handleReset() {
  resetSettings()
  form.value = { apiKey: '', baseUrl: '', model: '', systemPrompt: '' }
  modelOptions.value = []
  selectedProvider.value = 'custom'
  message.info('已重置')
}
</script>

<style scoped>
.setting-page {
  height: 100vh;
  background: linear-gradient(135deg, #0f0f14 0%, #1a1a2e 50%, #0f0f14 100%);
  display: flex;
  flex-direction: column;
  color: white;
}

.setting-card-wrapper {
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding: 16px 16px 0;
  overflow: hidden;
}

.setting-card {
  width: 100%;
  max-width: 520px;
  max-height: calc(100vh - 80px);
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  border-radius: 12px;
  background: rgba(24, 24, 32, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.06);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
}

.setting-card :deep(.n-card-header) {
  padding: 16px 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.setting-card :deep(.n-card-header__main) {
  color: #e0e0f0;
  font-size: 16px;
  font-weight: 600;
}

.setting-card :deep(.n-card__content) {
  padding: 16px 20px;
  flex: 1;
  overflow: hidden;
}

.scrollable-form {
  overflow-y: auto;
  overflow-x: hidden;
  max-height: calc(100vh - 180px);
  padding-right: 4px;
}

.scrollable-form::-webkit-scrollbar {
  width: 4px;
}

.scrollable-form::-webkit-scrollbar-track {
  background: transparent;
}

.scrollable-form::-webkit-scrollbar-thumb {
  background: rgba(99, 102, 241, 0.3);
  border-radius: 2px;
}

.scrollable-form::-webkit-scrollbar-thumb:hover {
  background: rgba(99, 102, 241, 0.5);
}

.provider-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  width: 100%;
}

.provider-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 10px 6px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  cursor: pointer;
  transition: all 0.2s ease;
  background: rgba(255, 255, 255, 0.02);
}

.provider-card:hover {
  border-color: rgba(99, 102, 241, 0.4);
  background: rgba(99, 102, 241, 0.06);
}

.provider-card.active {
  border-color: #6366f1;
  background: rgba(99, 102, 241, 0.12);
}

.provider-icon {
  font-size: 20px;
}

.provider-name {
  font-size: 11px;
  color: #a0a0b8;
  text-align: center;
}

.provider-card.active .provider-name {
  color: #c7d2fe;
}

.preset-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0;
  margin-top: 4px;
}
</style>