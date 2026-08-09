<template>
  <div class="setting-page">
    <TitleBar />
    <div class="setting-container">
      <!-- 外观设置卡片 -->
      <n-card :title="t('setting.appearance')" class="setting-card">
        <n-form label-placement="top">
          <n-form-item :label="t('setting.themeMode')">
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
                  <span class="theme-option-label">{{ t('setting.light') }}</span>
                  <span class="theme-option-desc">{{ t('setting.lightDesc') }}</span>
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
                    </div>
                  </div>
                </div>
                <div class="theme-option-meta">
                  <span class="theme-option-label">{{ t('setting.dark') }}</span>
                  <span class="theme-option-desc">{{ t('setting.darkDesc') }}</span>
                </div>
              </button>
            </div>
          </n-form-item>
          <n-text depth="3" style="font-size: 12px;">
            {{ t('setting.themeHint') }}
          </n-text>
        </n-form>
      </n-card>

      <!-- 任务完成提醒 -->
      <n-card :title="t('setting.notification')" class="setting-card">
        <n-form label-placement="top">
          <n-form-item :label="t('setting.notifyEnabled')">
            <div class="inline-row">
              <n-switch v-model:value="notifyForm.enabled" />
              <n-text depth="3" style="font-size: 12px;">
                {{ t('setting.notifyEnabledHint') }}
              </n-text>
            </div>
          </n-form-item>
          <n-form-item :label="t('setting.notifySound')">
            <n-switch
              v-model:value="notifyForm.soundEnabled"
              :disabled="!notifyForm.enabled"
            />
          </n-form-item>
          <n-form-item :label="t('setting.notifySoundSelect')">
            <div class="inline-row">
              <n-select
                v-model:value="notifyForm.soundId"
                :options="soundOptions"
                :disabled="!notifyForm.enabled || !notifyForm.soundEnabled"
                style="max-width: 260px;"
              />
              <n-button
                size="small"
                secondary
                :disabled="!notifyForm.enabled || !notifyForm.soundEnabled || notifyForm.soundId === 'none'"
                @click="previewSound"
              >
                {{ t('setting.previewSound') }}
              </n-button>
              <n-text depth="3" style="font-size: 12px; margin-top: 6px; display: block;">
              {{ t('setting.soundHint') }}
            </n-text>
            </div>
          </n-form-item>

          <n-form-item :label="t('setting.notifyVolume')">
            <n-slider
              v-model:value="notifyVolumePercent"
              :min="0"
              :max="100"
              :step="5"
              :disabled="!notifyForm.enabled || !notifyForm.soundEnabled"
              :format-tooltip="(v: number) => `${v}%`"
              style="max-width: 320px;"
            />
          </n-form-item>
          <n-form-item :label="t('setting.notifyDesktop')">
            <div class="inline-row">
              <n-switch
                v-model:value="notifyForm.desktopNotify"
                :disabled="!notifyForm.enabled"
              />
              <n-text depth="3" style="font-size: 12px;">
                {{ t('setting.notifyDesktopHint') }}
              </n-text>
            </div>
          </n-form-item>
          <n-form-item :label="t('setting.notifyBackgroundOnly')">
            <div class="inline-row">
              <n-switch
                v-model:value="notifyForm.onlyWhenBackground"
                :disabled="!notifyForm.enabled || !notifyForm.desktopNotify"
              />
              <n-text depth="3" style="font-size: 12px;">
                {{ t('setting.notifyBackgroundHint') }}
              </n-text>
            </div>
          </n-form-item>
          <n-space justify="end">
            <n-button
              secondary
              :disabled="!notifyForm.enabled"
              @click="testNotify"
            >
          {{ t('setting.testNotify') }}
            </n-button>
            <n-button @click="resetNotify">{{ t('setting.resetNotify') }}</n-button>
            <n-button type="primary" @click="saveNotify">{{ t('setting.saveNotify') }}</n-button>
          </n-space>
        </n-form>
      </n-card>


      <!-- STT 设置卡片 -->
      <n-card :title="t('setting.stt')" class="setting-card">
        <n-form :model="sttForm" label-placement="top">
          <n-form-item :label="t('setting.sttProvider')">
            <n-select
              v-model:value="sttForm.provider"
              :options="sttProviders"
              :placeholder="t('setting.sttProviderPlaceholder')"
            />
          </n-form-item>
          <n-form-item label="API Key">
            <n-input
              v-model:value="sttForm.apiKey"
              type="password"
              show-password-on="click"
              :placeholder="t('setting.sttApiKeyPlaceholder')"
            />
          </n-form-item>
          <n-form-item :label="t('setting.sttModel')">
            <n-input
              v-model:value="sttForm.model"
              :placeholder="t('setting.sttModelPlaceholder')"
            />
          </n-form-item>
          <n-form-item :label="t('setting.sttLanguage')">
            <n-select
              v-model:value="sttForm.language"
              :options="languageOptions"
              :placeholder="t('setting.sttLanguagePlaceholder')"
              clearable
            />
          </n-form-item>
          <n-space justify="end">
            <n-button @click="resetStt">{{ t('setting.sttReset') }}</n-button>
            <n-button type="primary" @click="saveStt">{{ t('setting.sttSave') }}</n-button>
          </n-space>
        </n-form>
      </n-card>

      <!-- TTS 设置卡片 -->
      <n-card :title="t('setting.tts')" class="setting-card">
        <n-form :model="ttsForm" label-placement="top">
          <n-form-item :label="t('setting.ttsProvider')">
            <n-select
              v-model:value="ttsForm.provider"
              :options="ttsProviders"
              :placeholder="t('setting.ttsProviderPlaceholder')"
            />
          </n-form-item>
          <n-form-item label="API Key">
            <n-input
              v-model:value="ttsForm.apiKey"
              type="password"
              show-password-on="click"
              :placeholder="t('setting.ttsApiKeyPlaceholder')"
            />
          </n-form-item>
          <n-form-item :label="t('setting.ttsModel')">
            <n-input
              v-model:value="ttsForm.model"
              :placeholder="t('setting.ttsModelPlaceholder')"
            />
          </n-form-item>
          <n-form-item :label="t('setting.ttsVoice')">
            <n-select
              v-model:value="ttsForm.voice"
              :options="voiceOptions"
              :placeholder="t('setting.ttsVoicePlaceholder')"
            />
          </n-form-item>
          <n-form-item :label="t('setting.ttsSpeed')">
            <n-slider
              v-model:value="ttsForm.speed"
              :min="0.25"
              :max="4.0"
              :step="0.25"
              :format-tooltip="(v: number) => v.toFixed(2) + 'x'"
            />
          </n-form-item>
          <n-space justify="end">
            <n-button @click="resetTts">{{ t('setting.ttsReset') }}</n-button>
            <n-button type="primary" @click="saveTts">{{ t('setting.ttsSave') }}</n-button>
          </n-space>
        </n-form>
      </n-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useMessage } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import TitleBar from '@/components/TitleBar.vue'
import { useTheme } from '@/composables/useTheme'
import {
  useNotify,
  playNotifySound,
  notifyTaskComplete,
  requestDesktopNotifyPermission,
  type NotifySettings,
  type NotifySoundId,
} from '@/composables/useNotify'

const message = useMessage()
const { t } = useI18n()
const { mode, setMode } = useTheme()
const {
  notifySettings,
  loadNotifySettings,
  saveNotifySettings,
  resetNotifySettings,
  defaultSettings,
} = useNotify()


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
  { label: 'Custom', value: 'custom' },
]

const ttsProviders = [
  { label: 'OpenAI TTS', value: 'openai' },
  { label: 'Azure Speech', value: 'azure' },
  { label: 'Google Text-to-Speech', value: 'google' },
  { label: 'Edge TTS', value: 'edge' },
  { label: 'Custom', value: 'custom' },
]
const languageOptions = computed(() => [
  { label: t('setting.langAuto'), value: 'auto' },
  { label: t('setting.langZhCN'), value: 'zh-CN' },
  { label: t('setting.langZhTW'), value: 'zh-TW' },
  { label: t('setting.langEn'), value: 'en' },
  { label: t('setting.langJa'), value: 'ja' },
  { label: t('setting.langKo'), value: 'ko' },
])

const voiceOptions = [
  { label: 'Alloy', value: 'alloy' },
  { label: 'Echo', value: 'echo' },
  { label: 'Fable', value: 'fable' },
  { label: 'Onyx', value: 'onyx' },
  { label: 'Nova', value: 'nova' },
  { label: 'Shimmer', value: 'shimmer' },
]

const soundOptions = computed<{ label: string; value: NotifySoundId }[]>(() => [
  { label: t('setting.soundRandom'), value: 'random' }, { label: t('setting.soundBreeze'), value: 'breeze' },
  { label: t('setting.soundDew'), value: 'dew' }, { label: t('setting.soundLullaby'), value: 'lullaby' },
  { label: t('setting.soundPetal'), value: 'petal' }, { label: t('setting.soundWarmth'), value: 'warmth' },
  { label: t('setting.soundRipple'), value: 'ripple' }, { label: t('setting.soundMist'), value: 'mist' },
  { label: t('setting.soundEmber'), value: 'ember' }, { label: t('setting.soundCloud'), value: 'cloud' },
  { label: t('setting.soundHush'), value: 'hush' }, { label: t('setting.soundDawn'), value: 'dawn' },
  { label: t('setting.soundSilk'), value: 'silk' }, { label: t('setting.soundMoon'), value: 'moon' },
  { label: t('setting.soundRain'), value: 'rain' }, { label: t('setting.soundNone'), value: 'none' },
])



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
const notifyForm = ref<NotifySettings>({ ...defaultSettings })

/** 滑块用 0–100，内部存 0–1 */
const notifyVolumePercent = computed({
  get: () => Math.round((notifyForm.value.volume ?? 0.38) * 100),

  set: (v: number) => {
    notifyForm.value.volume = Math.min(1, Math.max(0, v / 100))
  },
})

const STT_KEY = 'symbix_stt_settings'
const TTS_KEY = 'symbix_tts_settings'

onMounted(() => {
  loadNotifySettings()
  notifyForm.value = { ...notifySettings.value }

  try {
    const savedStt = localStorage.getItem(STT_KEY)
    if (savedStt) sttForm.value = JSON.parse(savedStt)
  } catch {}
  try {
    const savedTts = localStorage.getItem(TTS_KEY)
    if (savedTts) ttsForm.value = JSON.parse(savedTts)
  } catch {}
})
async function saveNotify() {

  saveNotifySettings({ ...notifyForm.value })
  if (notifyForm.value.desktopNotify) {
    const perm = await requestDesktopNotifyPermission()
    if (perm === 'denied') {
      message.warning(t('setting.notifyPermDenied'))
    } else if (perm === 'granted') {
      message.success(t('setting.notifySavedWithPerm'))
    } else {
      message.success(t('setting.notifySaved'))
    }
  } else {
    message.success(t('setting.notifySaved'))
  }
}

function resetNotify() {
  resetNotifySettings()
  notifyForm.value = { ...defaultSettings }
  message.info(t('setting.notifyReset'))
}

function previewSound() {
  // 先保存当前表单设置，确保试听音量与实际通知一致
  saveNotifySettings({ ...notifyForm.value })
  playNotifySound(notifyForm.value.soundId, notifyForm.value.volume)
}

async function testNotify() {
  // 先写入当前表单，便于立即按表单试听
  saveNotifySettings({ ...notifyForm.value })
  if (notifyForm.value.desktopNotify) {
    await requestDesktopNotifyPermission()
  }
  await notifyTaskComplete({
    title: t('chat.taskCompleteTitle'),
    body: t('setting.testNotifyBody'),
    forceDesktop: true,
  })
  message.info(t('setting.testNotifyTriggered'))
}


function saveStt() {
  localStorage.setItem(STT_KEY, JSON.stringify(sttForm.value))
  message.success(t('setting.sttSaved'))
}

function resetStt() {
  sttForm.value = { ...defaultStt }
  localStorage.removeItem(STT_KEY)
  message.info(t('setting.sttResetInfo'))
}

function saveTts() {
  localStorage.setItem(TTS_KEY, JSON.stringify(ttsForm.value))
  message.success(t('setting.ttsSaved'))
}

function resetTts() {
  ttsForm.value = { ...defaultTts }
  localStorage.removeItem(TTS_KEY)
  message.info(t('setting.ttsResetInfo'))
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

.inline-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
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
