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
      <!-- 界面语言设置卡片 -->
      <n-card :title="t('setting.language_settings')" class="setting-card">
        <n-form label-placement="top">
          <n-form-item :label="t('setting.language')">
            <n-select
              :value="locale"
              :options="uiLocaleOptions"
              style="max-width: 260px;"
              @update:value="onLocaleChange"
            />
          </n-form-item>
        </n-form>
        <n-text depth="3" style="font-size: 12px;">
          {{ t('setting.languageHint') }}
        </n-text>
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

      <!-- 弹幕设置卡片 -->
      <n-card :title="t('setting.companion')" class="setting-card">
        <n-form label-placement="top">
          <n-form-item :label="t('setting.companionEnabled')">
            <div class="inline-row">
              <n-switch
                v-model:value="companionForm.enabled"
                :loading="companionLoading"
                @update:value="onCompanionChange('enabled')"
              />
              <n-text depth="3" style="font-size: 12px;">
                {{ t('setting.companionEnabledHint') }}
              </n-text>
            </div>
          </n-form-item>
          <n-form-item :label="t('setting.companionIdle')">
            <div class="inline-row">
              <n-switch
                v-model:value="companionForm.idle_enabled"
                :disabled="!companionForm.enabled"
                :loading="companionLoading"
                @update:value="onCompanionChange('idle_enabled')"
              />
              <n-text depth="3" style="font-size: 12px;">
                {{ t('setting.companionIdleHint') }}
              </n-text>
            </div>
          </n-form-item>
          <n-form-item :label="t('setting.companionGreeting')">
            <div class="inline-row">
              <n-switch
                v-model:value="companionForm.greeting_enabled"
                :disabled="!companionForm.enabled"
                :loading="companionLoading"
                @update:value="onCompanionChange('greeting_enabled')"
              />
              <n-text depth="3" style="font-size: 12px;">
                {{ t('setting.companionGreetingHint') }}
              </n-text>
            </div>
          </n-form-item>
          <n-space justify="end">
            <n-button secondary :disabled="companionLoading" @click="testCompanion">
              {{ t('setting.companionTest') }}
            </n-button>
            <n-button secondary :disabled="companionLoading" @click="resetCompanion">
              {{ t('setting.companionReset') }}
            </n-button>
          </n-space>
        </n-form>
      </n-card>

      <!-- STT 设置卡片 -->
      <n-card :title="t('setting.stt')" class="setting-card">
        <n-space justify="space-between" align="center" style="padding: 0 0 12px 0">
          <span class="hint-text">{{ t('setting.sttEnabledHint') }}</span>
          <n-switch v-model:value="sttForm.enabled" />
        </n-space>
        <n-form :model="sttForm" label-placement="top" size="small" :disabled="!sttForm.enabled">
          <n-form-item :label="t('setting.voicePrimary')">
            <n-select
              v-model:value="sttForm.priority0"
              :options="sttPrimaryOptions"
              :placeholder="t('setting.sttProviderPlaceholder')"
            />
          </n-form-item>
          <n-form-item :label="t('setting.voiceSecondary')">
            <n-select
              v-model:value="sttForm.priority1"
              :options="sttSecondaryOptions"
              :placeholder="t('setting.voiceSecondaryHint')"
              clearable
            />
          </n-form-item>
          <n-form-item :label="t('setting.sttLanguage')">
            <n-select
              v-model:value="sttForm.language"
              :options="sttLanguageOptions"
            />
          </n-form-item>
          <n-form-item :label="t('setting.sttVad')">
            <n-space align="center" :wrap="false">
              <n-switch v-model:value="sttForm.use_vad" />
              <span class="hint-text">{{ t('setting.sttVadHint') }}</span>
            </n-space>
          </n-form-item>
          <n-collapse>
            <n-collapse-item :title="t('setting.advancedSettings')" name="stt-advanced">
              <n-form-item :label="t('setting.sttThreads')">
                <n-input-number v-model:value="sttForm.threads" :min="1" :max="32" />
              </n-form-item>
              <n-form-item :label="t('setting.sttDevice')">
                <n-space vertical style="width:100%">
                  <n-select
                    v-model:value="sttForm.capture_device"
                    :options="sttDeviceOptions"
                    :loading="sttDevicesLoading"
                    :consistent-menu-width="false"
                    style="width:100%"
                  />
                  <n-button
                    text
                    type="primary"
                    size="small"
                    :loading="sttDevicesLoading"
                    style="align-self:flex-start;padding:0"
                    @click="loadSttDevices"
                  >
                    {{ t('setting.sttDeviceRefresh') }}
                  </n-button>
                </n-space>
              </n-form-item>
              <template v-if="sttForm.use_vad">
                <n-form-item :label="t('setting.sttChunkSize')">
                  <n-input-number v-model:value="sttForm.chunk_size" :min="10" :max="1000" :step="10" />
                </n-form-item>
                <n-form-item :label="t('setting.sttMinMute')">
                  <n-input-number v-model:value="sttForm.min_mute_chunks" :min="1" :max="100" />
                </n-form-item>
                <n-form-item :label="t('setting.sttMaxNomute')">
                  <n-input-number v-model:value="sttForm.max_nomute_chunks" :min="1" :max="500" />
                </n-form-item>
              </template>
              <n-form-item :label="t('setting.sttUsePrefix')">
                <n-space align="center" :wrap="false">
                  <n-switch v-model:value="sttForm.use_prefix" />
                  <span class="hint-text">{{ t('setting.sttUsePrefixHint') }}</span>
                </n-space>
              </n-form-item>
              <n-form-item :label="t('setting.sttUseItn')">
                <n-switch v-model:value="sttForm.use_itn" />
              </n-form-item>
              <n-form-item :label="t('setting.sttNoGpu')">
                <n-switch v-model:value="sttForm.no_gpu" />
              </n-form-item>
              <n-form-item :label="t('setting.sttFlashAttn')">
                <n-switch v-model:value="sttForm.flash_attn" />
              </n-form-item>
            </n-collapse-item>
            <n-collapse-item :title="t('setting.cloudApi')" name="stt-cloud">
              <n-form-item :label="t('setting.cloudBaseUrl')">
                <n-input v-model:value="sttForm.openai_base_url" :placeholder="t('setting.cloudBaseUrlPlaceholderStt')" />
              </n-form-item>
              <n-form-item :label="t('setting.cloudApiKey')">
                <n-input v-model:value="sttForm.openai_api_key" type="password" show-password-on="click" :placeholder="t('setting.cloudApiKeyPlaceholder')" />
              </n-form-item>
              <n-form-item :label="t('setting.cloudModel')">
                <n-input v-model:value="sttForm.openai_model" :placeholder="t('setting.cloudModelPlaceholderStt')" />
              </n-form-item>
            </n-collapse-item>
          </n-collapse>
          <n-space justify="end">
            <n-button @click="resetStt">{{ t('setting.sttReset') }}</n-button>
            <n-button type="primary" :loading="sttSaving" @click="saveStt">{{ t('setting.sttSave') }}</n-button>
          </n-space>
        </n-form>
      </n-card>

      <!-- TTS 设置卡片 -->
      <n-card :title="t('setting.tts')" class="setting-card">
        <n-space justify="space-between" align="center" style="padding: 0 0 12px 0">
          <span class="hint-text">{{ t('setting.ttsEnabledHint') }}</span>
          <n-switch v-model:value="ttsForm.enabled" />
        </n-space>
        <n-space justify="space-between" align="center" style="padding: 0 0 12px 0">
          <span class="hint-text">{{ t('setting.readAloudHint') }}</span>
          <n-switch :value="readAloud" @update:value="setReadAloud" />
        </n-space>
        <!-- edge-tts 自愈:微软换令牌代次后旧版一律 403,开着就自动升库并重试一次 -->
        <template v-if="edgeInUse">
          <n-space justify="space-between" align="center" style="padding: 0 0 12px 0">
            <span class="hint-text">{{ t('setting.edgeAutoUpdateHint') }}</span>
            <n-switch :value="ttsForm.edge_auto_update" :disabled="!ttsForm.enabled" @update:value="setEdgeAutoUpdate" />
          </n-space>
          <n-space justify="space-between" align="center" style="padding: 0 0 12px 0">
            <span class="hint-text">
              {{ t('setting.edgeVersion') }} {{ edgeVersion || t('setting.edgeVersionUnknown') }}
            </span>
            <n-button size="small" :loading="edgeUpgrading" :disabled="!ttsForm.enabled" @click="upgradeEdge">
              {{ t('setting.edgeUpgrade') }}
            </n-button>
          </n-space>
        </template>
        <n-form :model="ttsForm" label-placement="top" size="small" :disabled="!ttsForm.enabled">
          <n-form-item :label="t('setting.voicePrimary')">
            <n-select
              v-model:value="ttsForm.priority0"
              :options="ttsPrimaryOptions"
              :placeholder="t('setting.ttsProviderPlaceholder')"
            />
          </n-form-item>
          <n-form-item :label="t('setting.voiceSecondary')">
            <n-select
              v-model:value="ttsForm.priority1"
              :options="ttsSecondaryOptions"
              :placeholder="t('setting.voiceSecondaryHint')"
              clearable
            />
          </n-form-item>
          <n-form-item v-if="ttsForm.priority0 !== 'custom'" :label="t('setting.ttsVoice')">
            <n-select
              v-model:value="ttsForm.voice"
              :options="ttsVoiceOptions"
              :placeholder="t('setting.ttsVoicePlaceholder')"
              filterable
            />
          </n-form-item>
          <n-form-item v-else :label="t('setting.ttsCustomSpeaker')">
            <n-input
              v-model:value="ttsForm.voice"
              :placeholder="t('setting.ttsCustomSpeakerPlaceholder')"
            />
          </n-form-item>
          <n-form-item :label="t('setting.ttsSpeed')">
            <n-slider
              v-model:value="ttsForm.speed"
              :min="0.5"
              :max="2.0"
              :step="0.05"
              :format-tooltip="(v: number) => v.toFixed(2) + 'x'"
            />
          </n-form-item>
          <n-collapse>
            <n-collapse-item :title="t('setting.cloudApi')" name="tts-cloud">
              <n-form-item :label="t('setting.cloudBaseUrl')">
                <n-input v-model:value="ttsForm.openai_base_url" :placeholder="t('setting.cloudBaseUrlPlaceholderTts')" />
              </n-form-item>
              <n-form-item :label="t('setting.cloudApiKey')">
                <n-input v-model:value="ttsForm.openai_api_key" type="password" show-password-on="click" :placeholder="t('setting.cloudApiKeyPlaceholder')" />
              </n-form-item>
              <n-form-item :label="t('setting.cloudModel')">
                <n-input v-model:value="ttsForm.openai_model" :placeholder="t('setting.cloudModelPlaceholderTts')" />
              </n-form-item>
            </n-collapse-item>
            <n-collapse-item :title="t('setting.ttsCustom')" name="tts-custom">
              <n-form-item :label="t('setting.ttsCustomServers')">
                <n-space vertical style="width: 100%">
                  <n-input
                    v-model:value="ttsForm.custom_servers"
                    type="textarea"
                    :rows="3"
                    :placeholder="t('setting.ttsCustomServersPlaceholder')"
                  />
                  <span class="hint-text">{{ t('setting.ttsCustomServersHint') }}</span>
                </n-space>
              </n-form-item>
            </n-collapse-item>
          </n-collapse>
          <n-space justify="end" align="center">
            <n-button :loading="ttsPreviewing" @click="previewTts">{{ t('setting.voicePreview') }}</n-button>
            <n-button @click="resetTts">{{ t('setting.ttsReset') }}</n-button>
            <n-button type="primary" :loading="ttsSaving" @click="saveTts">{{ t('setting.ttsSave') }}</n-button>
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
import { useLocale } from '@/composables/useLocale'
import { useCompanion, type CompanionSettings } from '@/composables/useCompanion'
import { useReadAloud } from '@/composables/useReadAloud'
import {
  useNotify,
  playNotifySound,
  notifyTaskComplete,
  requestDesktopNotifyPermission,
  type NotifySettings,
  type NotifySoundId,
} from '@/composables/useNotify'
import {
  getVoiceConfig,
  updateVoiceConfig,
  listSttDevices,
  previewTts as previewTtsApi,
  upgradeEdgeTts,
  setEdgeAutoUpdate as setEdgeAutoUpdateApi,
  type VoiceConfigResp,
} from '@/utils/backend'

const message = useMessage()
const { t } = useI18n()
const { readAloud, setReadAloud } = useReadAloud()
const { mode, setMode } = useTheme()
const { locale, localeOptions: uiLocaleOptions, setLocale } = useLocale()
const {
  notifySettings,
  loadNotifySettings,
  saveNotifySettings,
  resetNotifySettings,
  defaultSettings,
} = useNotify()
const companion = useCompanion()
const companionForm = ref<CompanionSettings>({ ...companion.defaultSettings })
const companionLoading = ref(false)

async function loadCompanionForm() {
  companionLoading.value = true
  try {
    await companion.loadCompanionSettings()
    companionForm.value = { ...companion.companionSettings.value }
  } finally {
    companionLoading.value = false
  }
}

function onCompanionChange(key: keyof CompanionSettings) {
  void companion.saveCompanionSettings({ [key]: companionForm.value[key] })
}

async function resetCompanion() {
  companionLoading.value = true
  try {
    await companion.resetCompanionSettings()
    companionForm.value = { ...companion.defaultSettings }
  } finally {
    companionLoading.value = false
  }
}

async function testCompanion() {
  const ok = await companion.testDanmaku()
  if (ok) {
    message.success(t('setting.companionTestTriggered'))
  } else {
    message.error(t('setting.companionTestFailed'))
  }
}

function onLocaleChange(value: string) {
  setLocale(value)
  message.success(t('setting.languageChanged'))
}


interface SttSettings {
  enabled: boolean
  priority0: string
  priority1: string | null
  language: string
  threads: number
  use_vad: boolean
  chunk_size: number
  min_mute_chunks: number
  max_nomute_chunks: number
  use_prefix: boolean
  use_itn: boolean
  capture_device: number
  no_gpu: boolean
  flash_attn: boolean
  openai_base_url: string
  openai_api_key: string
  openai_model: string
}

interface TtsSettings {
  enabled: boolean
  priority0: string
  priority1: string | null
  voice: string
  speed: number
  openai_base_url: string
  openai_api_key: string
  openai_model: string
  custom_servers: string
  edge_auto_update: boolean
}

// 后端 /voice/config 返回的引擎可用状态
const ttsStatus = ref<Record<string, { available: boolean; voices: { value: string; label: string }[] }>>({})
const sttStatus = ref<Record<string, { available: boolean; cloud: boolean }>>({})

// ---- 本机麦克风设备枚举(替代手填设备 ID) ----
const sttDeviceOptions = ref<{ label: string; value: number; title?: string }[]>([])
const sttDevicesLoading = ref(false)

/** 拉取本机音频捕获设备列表,生成下拉选项(含"系统默认")。 */
async function loadSttDevices() {
  sttDevicesLoading.value = true
  try {
    const devs = await listSttDevices()
    sttDeviceOptions.value = [
      { label: t('setting.sttDeviceDefault'), value: -1 },
      ...devs.map(d => ({ label: `${d.name} (#${d.id})`, value: d.id, title: d.name })),
    ]
  } catch {
    // 枚举失败(引擎不可用等)时保留默认项,不阻断设置页
    sttDeviceOptions.value = [{ label: t('setting.sttDeviceDefault'), value: -1 }]
  } finally {
    sttDevicesLoading.value = false
  }
}

const STT_ENGINE_LABELS: Record<string, string> = {
  sensevoice: 'SenseVoice (本地)',
  openai: 'OpenAI 兼容 (云)',
}
const TTS_ENGINE_LABELS: Record<string, string> = {
  edge: 'Edge-TTS (云)',
  openai: 'OpenAI 兼容 (云)',
  custom: '自定义 HTTP (本地/自建)',
}

function defaultStt(): SttSettings {
  return {
    enabled: true,
    priority0: 'sensevoice',
    priority1: null,
    language: 'auto',
    threads: 4,
    use_vad: true,
    chunk_size: 100,
    min_mute_chunks: 10,
    max_nomute_chunks: 80,
    use_prefix: true,
    use_itn: true,
    capture_device: -1,
    no_gpu: false,
    flash_attn: false,
    openai_base_url: '',
    openai_api_key: '',
    openai_model: 'whisper-1',
  }
}
function defaultTts(): TtsSettings {
  return { enabled: true, priority0: 'edge', priority1: null, voice: '', speed: 1.0, openai_base_url: '', openai_api_key: '', openai_model: 'tts-1', custom_servers: '', edge_auto_update: true }
}

const sttForm = ref<SttSettings>(defaultStt())
const ttsForm = ref<TtsSettings>(defaultTts())
const notifyForm = ref<NotifySettings>({ ...defaultSettings })
const sttSaving = ref(false)
const ttsSaving = ref(false)
const ttsPreviewing = ref(false)

// ---- edge-tts(云端)版本 + 手动升级 ----
// 微软会周期性轮换 Sec-MS-GEC 令牌代次,旧版 edge-tts 一律 403。引擎侧能自愈,
// 这里给用户一个「看版本 + 一键升级」的兜底入口。
const edgeVersion = ref('')
const edgeUpgrading = ref(false)
/** 主/备引擎里有 edge 时才显示上面两个入口 */
const edgeInUse = computed(() => [ttsForm.value.priority0, ttsForm.value.priority1].includes('edge'))

/** 「自动更新 edge-tts」开关:改动立即落盘,不必再点「保存 TTS 设置」;失败回滚。 */
async function setEdgeAutoUpdate(next: boolean) {
  const prev = ttsForm.value.edge_auto_update
  ttsForm.value.edge_auto_update = next
  try {
    ttsForm.value.edge_auto_update = await setEdgeAutoUpdateApi(next)
  } catch (e) {
    ttsForm.value.edge_auto_update = prev
    message.error(t('setting.edgeAutoUpdateFail', { detail: String((e as Error)?.message || e) }))
  }
}

async function upgradeEdge() {
  edgeUpgrading.value = true
  try {
    const r = await upgradeEdgeTts()
    if (r.ok) {
      edgeVersion.value = r.installed || edgeVersion.value
      message.success(t('setting.edgeUpgradeOk', { ver: r.installed || '?' }))
      await loadVoiceConfig()
    } else {
      message.error(t('setting.edgeUpgradeFail', { detail: r.detail }))
    }
  } catch (e) {
    message.error(String((e as Error)?.message || e))
  } finally {
    edgeUpgrading.value = false
  }
}

// STT 语言下拉(对齐 SenseVoice: zh/en/yue/ja/ko + auto)
const sttLanguageOptions = computed(() => [
  { label: t('setting.langAuto'), value: 'auto' },
  { label: t('setting.langZhCN'), value: 'zh' },
  { label: t('setting.sttLangYue'), value: 'yue' },
  { label: t('setting.langEn'), value: 'en' },
  { label: t('setting.langJa'), value: 'ja' },
  { label: t('setting.langKo'), value: 'ko' },
])

const sttPrimaryOptions = computed(() =>
  Object.entries(sttStatus.value).map(([name, info]) => ({
    label: `${STT_ENGINE_LABELS[name] || name} — ${info.available ? t('setting.voiceEngineAvail') : t('setting.voiceEngineUnavail')}`,
    value: name,
    disabled: !info.available,
  })),
)
const sttSecondaryOptions = computed(() =>
  Object.entries(sttStatus.value)
    .filter(([name]) => name !== sttForm.value.priority0)
    .map(([name, info]) => ({
      label: `${STT_ENGINE_LABELS[name] || name} — ${info.available ? t('setting.voiceEngineAvail') : t('setting.voiceEngineUnavail')}`,
      value: name,
      disabled: !info.available,
    })),
)
const ttsPrimaryOptions = computed(() =>
  Object.entries(ttsStatus.value).map(([name, info]) => ({
    label: `${TTS_ENGINE_LABELS[name] || name} — ${info.available ? t('setting.voiceEngineAvail') : t('setting.voiceEngineUnavail')}`,
    value: name,
    disabled: !info.available,
  })),
)
const ttsSecondaryOptions = computed(() =>
  Object.entries(ttsStatus.value)
    .filter(([name]) => name !== ttsForm.value.priority0)
    .map(([name, info]) => ({
    label: `${TTS_ENGINE_LABELS[name] || name} — ${info.available ? t('setting.voiceEngineAvail') : t('setting.voiceEngineUnavail')}`,
    value: name,
    disabled: !info.available,
  })),
)

// 主引擎对应音色列表(edge/openai 不同)
const ttsVoiceOptions = computed(() => {
  const cur = ttsForm.value.priority0
  const s = ttsStatus.value[cur]
  return (s?.voices || []).filter(v => !!v.value)
})

// 主/备引擎改变后,音色不再匹配则清空(custom 的 speaker 是自由文本,不动)
function fixTtsVoice() {
  if (ttsForm.value.priority0 === 'custom') return
  const cur = ttsForm.value.voice
  if (cur && !ttsVoiceOptions.value.some(o => o.value === cur)) {
    ttsForm.value.voice = ttsVoiceOptions.value[0]?.value || ''
  }
}

async function loadVoiceConfig() {
  try {
    const cfg: VoiceConfigResp = await getVoiceConfig()
    ttsStatus.value = cfg.status?.tts || {}
    sttStatus.value = cfg.status?.stt || {}
    edgeVersion.value = cfg.status?.edgeVersion || ''
    const stt = cfg.stt || {}
    sttForm.value = {
      enabled: stt.enabled ?? true,
      priority0: stt.priority?.[0] || 'sensevoice',
      priority1: stt.priority?.[1] || null,
      language: stt.language || 'auto',
      threads: stt.threads ?? 4,
      use_vad: stt.use_vad ?? true,
      chunk_size: stt.chunk_size ?? 100,
      min_mute_chunks: stt.min_mute_chunks ?? 10,
      max_nomute_chunks: stt.max_nomute_chunks ?? 80,
      use_prefix: stt.use_prefix ?? true,
      use_itn: stt.use_itn ?? true,
      capture_device: stt.capture_device ?? -1,
      no_gpu: stt.no_gpu ?? false,
      flash_attn: stt.flash_attn ?? false,
      openai_base_url: stt.openai_base_url || '',
      openai_api_key: stt.openai_api_key || '',
      openai_model: stt.openai_model || 'whisper-1',
    }
    const tts = cfg.tts || {}
    const ttsPriority0 = tts.priority?.[0] || 'edge'
    ttsForm.value = {
      enabled: (tts as any).enabled ?? true,
      priority0: ttsPriority0,
      priority1: tts.priority?.[1] || null,
      // 音色按主引擎取对应字段(voice_edge / voice_openai / voice_custom)
      voice: (tts as any)[`voice_${ttsPriority0}`] || '',
      speed: tts.speed ?? 1.0,
      openai_base_url: (tts as any).openai_base_url || '',
      openai_api_key: (tts as any).openai_api_key || '',
      openai_model: (tts as any).openai_model || 'tts-1',
      custom_servers: (tts as any).custom_servers || '',
      edge_auto_update: (tts as any).edge_auto_update ?? true,
    }
    fixTtsVoice()
  } catch {
    message.error(t('setting.voiceLoadFail'))
  }
}

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

/** 滑块用 0–100，内部存 0–1 */
const notifyVolumePercent = computed({
  get: () => Math.round((notifyForm.value.volume ?? 0.38) * 100),

  set: (v: number) => {
    notifyForm.value.volume = Math.min(1, Math.max(0, v / 100))
  },
})
onMounted(() => {
  loadNotifySettings()
  notifyForm.value = { ...notifySettings.value }
  loadVoiceConfig()
  loadSttDevices()
  void loadCompanionForm()
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


function buildSttPatch() {
  const f = sttForm.value
  const priority = [f.priority0, ...(f.priority1 ? [f.priority1] : [])].filter(Boolean) as string[]
    return {
    enabled: f.enabled,
    priority,
    language: f.language,
    threads: f.threads,
    use_vad: f.use_vad,
    chunk_size: f.chunk_size,
    min_mute_chunks: f.min_mute_chunks,
    max_nomute_chunks: f.max_nomute_chunks,
    use_prefix: f.use_prefix,
    use_itn: f.use_itn,
    capture_device: f.capture_device,
    no_gpu: f.no_gpu,
    flash_attn: f.flash_attn,
    openai_base_url: f.openai_base_url,
    openai_api_key: f.openai_api_key,
    openai_model: f.openai_model,
  }
}
function buildTtsPatch() {
  const f = ttsForm.value
  const priority = [f.priority0, ...(f.priority1 ? [f.priority1] : [])].filter(Boolean) as string[]
    const patch: Record<string, unknown> = { enabled: f.enabled, priority, speed: f.speed }
  // 音色按主引擎名字存到对应字段
  if (f.voice) patch[`voice_${f.priority0}`] = f.voice
  patch.openai_base_url = f.openai_base_url
  patch.openai_api_key = f.openai_api_key
  patch.openai_model = f.openai_model
  patch.custom_servers = f.custom_servers
  patch.edge_auto_update = f.edge_auto_update
  return patch
}

async function saveStt() {
  sttSaving.value = true
  try {
    await updateVoiceConfig({ stt: buildSttPatch() })
    await loadVoiceConfig()
    message.success(t('setting.voiceSaved'))
  } catch (e) {
    message.error(t('setting.voiceLoadFail'))
  } finally {
    sttSaving.value = false
  }
}

function resetStt() {
  sttForm.value = defaultStt()
  message.info(t('setting.sttResetInfo'))
}

async function saveTts() {
  ttsSaving.value = true
  try {
    await updateVoiceConfig({ tts: buildTtsPatch() })
    await loadVoiceConfig()
    message.success(t('setting.voiceSaved'))
  } catch (e) {
    message.error(t('setting.voiceLoadFail'))
  } finally {
    ttsSaving.value = false
  }
}

function resetTts() {
  ttsForm.value = defaultTts()
  fixTtsVoice()
  message.info(t('setting.ttsResetInfo'))
}

let ttsAudio: HTMLAudioElement | null = null

async function previewTts() {
  ttsPreviewing.value = true
  try {
    // 先保存当前设置,保证试听用新音色/语速
    await updateVoiceConfig({ tts: buildTtsPatch() })
    const url = await previewTtsApi(t('setting.voicePreviewText'), ttsForm.value.speed)
    if (ttsAudio) { ttsAudio.pause(); ttsAudio = null }
    ttsAudio = new Audio(url)
    ttsAudio.onended = () => { URL.revokeObjectURL(url) }
    await ttsAudio.play()
  } catch (e) {
    // 后端把引擎失败原因放在 detail 里(可能很长,如 edge 403 的处置建议),用弹窗完整展示
    ;(window as any).$dialog?.error?.({
      title: t('setting.voicePreviewFail'),
      content: String((e as Error)?.message || e),
    })
  } finally {
    ttsPreviewing.value = false
  }
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

.hint-text {
  font-size: 12px;
  color: var(--text-muted);
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
