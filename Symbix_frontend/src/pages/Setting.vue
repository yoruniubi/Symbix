<template>
  <div class="setting-page">
    <TitleBar />
    <div class="setting-container">
      <!-- 外观设置卡片 -->
      <n-card title="外观" class="setting-card">
        <n-form label-placement="top">
          <n-form-item label="主题模式">
            <div class="theme-options">
              <button
                type="button"
                class="theme-option"
                :class="{ active: mode === 'light' }"
                @click="setMode('light')"
              >
                <div class="theme-preview light-preview">
                  <div class="preview-bar"></div>
                  <div class="preview-body">
                    <div class="preview-sidebar"></div>
                    <div class="preview-main">
                      <div class="preview-line short"></div>
                      <div class="preview-line"></div>
                      <div class="preview-line mid"></div>
                    </div>
                  </div>
                </div>
                <div class="theme-option-meta">
                  <span class="theme-option-label">浅色</span>
                  <span class="theme-option-desc">温暖明亮，默认推荐</span>
                </div>
              </button>

              <button
                type="button"
                class="theme-option"
                :class="{ active: mode === 'dark' }"
                @click="setMode('dark')"
              >
                <div class="theme-preview dark-preview">
                  <div class="preview-bar"></div>
                  <div class="preview-body">
                    <div class="preview-sidebar"></div>
                    <div class="preview-main">
                      <div class="preview-line short"></div>
                      <div class="preview-line"></div>
                      <div class="preview-line mid"></div>
                    </div>
                  </div>
                </div>
                <div class="theme-option-meta">
                  <span class="theme-option-label">深色</span>
                  <span class="theme-option-desc">暖炭色调，贴近品牌色</span>
                </div>
              </button>
            </div>
          </n-form-item>
          <n-text depth="3" style="font-size: 12px;">
            主题会立即生效，并同步到对话窗口与桌宠界面。
          </n-text>
        </n-form>
      </n-card>

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
import { useTheme } from '@/composables/useTheme'

const message = useMessage()
const { mode, setMode } = useTheme()

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
  background: var(--bg-app);
  padding-top: 32px;
  color: var(--text-primary);
  overflow-y: auto;
}

.setting-container {
  max-width: 560px;
  margin: 40px auto;
  display: flex;
  flex-direction: column;
  gap: 24px;
  padding: 0 16px 40px;
}

.setting-card {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg, 12px);
}

/* ---- Theme options ---- */
.theme-options {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  width: 100%;
}

.theme-option {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border-radius: var(--radius-md, 8px);
  border: 1.5px solid var(--border);
  background: var(--bg-app);
  cursor: pointer;
  text-align: left;
  transition: all var(--duration-base, 180ms) var(--ease-standard, ease);
  color: inherit;
  font: inherit;
}

.theme-option:hover {
  border-color: var(--accent-border);
  background: var(--surface-hover);
}

.theme-option.active {
  border-color: var(--accent-500, #EF6B6E);
  box-shadow: 0 0 0 1px var(--accent-500, #EF6B6E), var(--shadow-sm);
  background: var(--accent-soft);
}

.theme-preview {
  height: 72px;
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid rgba(0, 0, 0, 0.06);
  display: flex;
  flex-direction: column;
}

.light-preview {
  background: #FBFAF9;
}
.light-preview .preview-bar {
  background: #FFFFFF;
  border-bottom: 1px solid #DCD7D2;
}
.light-preview .preview-sidebar {
  background: #FFFFFF;
  border-right: 1px solid #DCD7D2;
}
.light-preview .preview-main {
  background: #FBFAF9;
}
.light-preview .preview-line {
  background: #DCD7D2;
}
.light-preview .preview-line.short {
  background: #EF6B6E;
}

.dark-preview {
  background: #161210;
}
.dark-preview .preview-bar {
  background: rgba(30, 25, 22, 0.97);
  border-bottom: 1px solid #3D322C;
}
.dark-preview .preview-sidebar {
  background: rgba(22, 18, 16, 0.92);
  border-right: 1px solid #3D322C;
}
.dark-preview .preview-main {
  background: #161210;
}
.dark-preview .preview-line {
  background: #3D322C;
}
.dark-preview .preview-line.short {
  background: #EF6B6E;
}

.preview-bar {
  height: 10px;
  flex-shrink: 0;
}

.preview-body {
  flex: 1;
  display: flex;
  min-height: 0;
}

.preview-sidebar {
  width: 22%;
  flex-shrink: 0;
}

.preview-main {
  flex: 1;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 5px;
  justify-content: center;
}

.preview-line {
  height: 6px;
  border-radius: 3px;
  width: 100%;
}
.preview-line.short {
  width: 42%;
}
.preview-line.mid {
  width: 70%;
}

.theme-option-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.theme-option-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.theme-option-desc {
  font-size: 11px;
  color: var(--text-muted);
}
</style>
