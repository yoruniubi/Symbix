<template>
  <div class="setting-page">
    <TitleBar />
    <div class="setting-container">
      <!-- STT 设置卡片 -->
      <n-card title="语音识别 (STT)" class="setting-card">
        <n-form :model="sttForm" label-placement="top">
          <n-form-item label="STT 服务商">
            <n-select
              v-model:value="sttForm.provider"
              :options="sttProviders"
              placeholder="选择 STT 服务商"
            />
          </n-form-item>
          <n-form-item label="API Key">
            <n-input
              v-model:value="sttForm.apiKey"
              type="password"
              show-password-on="click"
              placeholder="输入 STT API Key"
            />
          </n-form-item>
          <n-form-item label="模型">
            <n-input
              v-model:value="sttForm.model"
              placeholder="例如 whisper-1"
            />
          </n-form-item>
          <n-form-item label="语言">
            <n-select
              v-model:value="sttForm.language"
              :options="languageOptions"
              placeholder="选择识别语言（可选）"
              clearable
            />
          </n-form-item>
          <n-space justify="end">
            <n-button @click="resetStt">重置</n-button>
            <n-button type="primary" @click="saveStt">保存 STT 设置</n-button>
          </n-space>
        </n-form>
      </n-card>

      <!-- TTS 设置卡片 -->
      <n-card title="语音合成 (TTS)" class="setting-card">
        <n-form :model="ttsForm" label-placement="top">
          <n-form-item label="TTS 服务商">
            <n-select
              v-model:value="ttsForm.provider"
              :options="ttsProviders"
              placeholder="选择 TTS 服务商"
            />
          </n-form-item>
          <n-form-item label="API Key">
            <n-input
              v-model:value="ttsForm.apiKey"
              type="password"
              show-password-on="click"
              placeholder="输入 TTS API Key"
            />
          </n-form-item>
          <n-form-item label="模型">
            <n-input
              v-model:value="ttsForm.model"
              placeholder="例如 tts-1"
            />
          </n-form-item>
          <n-form-item label="语音">
            <n-select
              v-model:value="ttsForm.voice"
              :options="voiceOptions"
              placeholder="选择语音"
            />
          </n-form-item>
          <n-form-item label="语速">
            <n-slider
              v-model:value="ttsForm.speed"
              :min="0.25"
              :max="4.0"
              :step="0.25"
              :format-tooltip="(v: number) => v.toFixed(2) + 'x'"
            />
          </n-form-item>
          <n-space justify="end">
            <n-button @click="resetTts">重置</n-button>
            <n-button type="primary" @click="saveTts">保存 TTS 设置</n-button>
          </n-space>
        </n-form>
      </n-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useMessage } from 'naive-ui'
import TitleBar from '@/components/TitleBar.vue'

const message = useMessage()

interface SttSettings {
  provider: string
  apiKey: string
  model: string
  language: string | null
}

interface TtsSettings {
  provider: string
  apiKey: string
  model: string
  voice: string
  speed: number
}

const sttProviders = [
  { label: 'OpenAI Whisper', value: 'openai' },
  { label: 'Azure Speech', value: 'azure' },
  { label: 'Google Speech-to-Text', value: 'google' },
  { label: '自定义', value: 'custom' },
]

const ttsProviders = [
  { label: 'OpenAI TTS', value: 'openai' },
  { label: 'Azure Speech', value: 'azure' },
  { label: 'Google Text-to-Speech', value: 'google' },
  { label: 'Edge TTS', value: 'edge' },
  { label: '自定义', value: 'custom' },
]

const languageOptions = [
  { label: '自动检测', value: 'auto' },
  { label: '中文（简体）', value: 'zh-CN' },
  { label: '中文（繁体）', value: 'zh-TW' },
  { label: 'English', value: 'en' },
  { label: '日本語', value: 'ja' },
  { label: '한국어', value: 'ko' },
]

const voiceOptions = [
  { label: 'Alloy', value: 'alloy' },
  { label: 'Echo', value: 'echo' },
  { label: 'Fable', value: 'fable' },
  { label: 'Onyx', value: 'onyx' },
  { label: 'Nova', value: 'nova' },
  { label: 'Shimmer', value: 'shimmer' },
]

const defaultStt: SttSettings = {
  provider: 'openai',
  apiKey: '',
  model: 'whisper-1',
  language: 'auto',
}

const defaultTts: TtsSettings = {
  provider: 'openai',
  apiKey: '',
  model: 'tts-1',
  voice: 'alloy',
  speed: 1.0,
}

const sttForm = ref<SttSettings>({ ...defaultStt })
const ttsForm = ref<TtsSettings>({ ...defaultTts })

const STT_KEY = 'symbix_stt_settings'
const TTS_KEY = 'symbix_tts_settings'

onMounted(() => {
  try {
    const savedStt = localStorage.getItem(STT_KEY)
    if (savedStt) sttForm.value = JSON.parse(savedStt)
  } catch {}
  try {
    const savedTts = localStorage.getItem(TTS_KEY)
    if (savedTts) ttsForm.value = JSON.parse(savedTts)
  } catch {}
})

function saveStt() {
  localStorage.setItem(STT_KEY, JSON.stringify(sttForm.value))
  message.success('STT 设置已保存')
}

function resetStt() {
  sttForm.value = { ...defaultStt }
  localStorage.removeItem(STT_KEY)
  message.info('STT 设置已重置')
}

function saveTts() {
  localStorage.setItem(TTS_KEY, JSON.stringify(ttsForm.value))
  message.success('TTS 设置已保存')
}

function resetTts() {
  ttsForm.value = { ...defaultTts }
  localStorage.removeItem(TTS_KEY)
  message.info('TTS 设置已重置')
}
</script>

<style scoped>
.setting-page {
  height: 100vh;
  background-color: rgba(16, 16, 20, 0.95);
  padding-top: 32px;
  color: white;
  overflow-y: auto;
}

.setting-container {
  max-width: 560px;
  margin: 40px auto;
  display: flex;
  flex-direction: column;
  gap: 24px;
  padding: 0 16px;
}

.setting-card {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
}
</style>