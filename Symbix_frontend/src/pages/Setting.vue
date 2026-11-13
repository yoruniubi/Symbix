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
            <n-button secondary :disabled="companionLoading" @click="testProactive">
              {{ t('setting.companionProactiveTest') }}
            </n-button>
            <n-button secondary :disabled="companionLoading" @click="resetCompanion">
              {{ t('setting.companionReset') }}
            </n-button>
          </n-space>
        </n-form>
      </n-card>

      <!-- 长任务设置卡片(轮次上限 / 累积工具结果预算) -->
      <n-card :title="t('setting.longTask')" class="setting-card">
        <n-form label-placement="top">
          <n-form-item :label="t('setting.longTaskMode')">
            <n-select
              v-model:value="longTaskMode"
              :options="longTaskOptions"
              :loading="longTaskLoading"
              :disabled="longTaskLoading"
              style="max-width: 280px;"
              @update:value="onLongTaskModeChange"
            />
          </n-form-item>
          <n-text depth="3" style="font-size: 12px; display: block;">
            {{ longTaskHint }}
          </n-text>
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
        <n-form label-placement="top">
          <n-form-item :label="t('setting.ttsEnabled')">
            <n-switch v-model:value="ttsForm.enabled" />
          </n-form-item>
          <n-form-item :label="t('setting.readAloud')">
            <n-switch :value="readAloud" @update:value="setReadAloud" />
          </n-form-item>
        </n-form>
        <n-form :model="ttsForm" label-placement="top" size="small" :disabled="!ttsForm.enabled">
          <n-form-item :label="t('setting.voicePrimary')">
            <n-select
              v-model:value="ttsForm.priority0"
              :options="ttsPrimaryOptions"
              :placeholder="t('setting.ttsProviderPlaceholder')"
              @update:value="fixTtsVoice"
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
          <!-- OpenAI 兼容引擎的音色写在请求体模板里（如 fish 的 reference_id），这里再选一次只会互相矛盾 -->
          <n-form-item v-if="ttsForm.priority0 === 'edge'" :label="t('setting.ttsVoice')">
            <n-select
              v-model:value="ttsForm.voice"
              :options="ttsVoiceOptions"
              :placeholder="t('setting.ttsVoicePlaceholder')"
              filterable
            />
          </n-form-item>
          <n-form-item v-else-if="ttsForm.priority0 === 'custom'" :label="t('setting.ttsCustomSpeaker')">
            <n-input
              v-model:value="ttsForm.voice"
              :placeholder="t('setting.ttsCustomSpeakerPlaceholder')"
            />
          </n-form-item>
          <div v-else class="hint-text tts-voice-note">{{ t('setting.ttsVoiceByTemplate') }}</div>
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
              <n-form-item :label="t('setting.probeLabel')">
                <n-space align="center" :size="8" style="width: 100%">
                  <n-button size="small" :loading="ttsProbing" @click="runTtsProbe">{{ t('setting.probeBtn') }}</n-button>
                  <n-button size="small" quaternary @click="curlVisible = true">{{ t('setting.curlBtn') }}</n-button>
                  <span class="hint-text">{{ t('setting.probeHint') }}</span>
                </n-space>
              </n-form-item>
              <n-form-item :label="t('setting.cloudApiKey')">
                <n-input v-model:value="ttsForm.openai_api_key" type="password" show-password-on="click" :placeholder="t('setting.cloudApiKeyPlaceholder')" />
              </n-form-item>
              <n-form-item :label="t('setting.cloudModel')">
                <n-space vertical style="width: 100%">
                  <n-input v-model:value="ttsForm.openai_model" :placeholder="t('setting.cloudModelPlaceholderTts')" />
                  <span class="hint-text" :class="{ 'is-warn': modelHintWarn }">{{ modelHint }}</span>
                </n-space>
              </n-form-item>
              <n-form-item :label="t('setting.extraHeaders')">
                <n-space vertical style="width: 100%">
                  <n-input
                    v-model:value="ttsForm.openai_extra_headers"
                    type="textarea"
                    :rows="3"
                    :placeholder="EXTRA_HEADERS_PLACEHOLDER"
                    class="json-input"
                  />
                  <span class="hint-text">{{ t('setting.extraHeadersHint') }}</span>
                </n-space>
              </n-form-item>
              <n-form-item :label="t('setting.bodyTemplate')">
                <n-space vertical style="width: 100%">
                  <n-input
                    v-model:value="ttsForm.openai_body_template"
                    type="textarea"
                    :rows="6"
                    :placeholder="BODY_TEMPLATE_PLACEHOLDER"
                    class="json-input"
                  />
                  <span class="hint-text">{{ t('setting.bodyTemplateHint') }}</span>
                </n-space>
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
          <div class="hint-text tts-preview-hint">{{ t('setting.ttsPreviewHint') }}</div>
          <n-space justify="end" align="center">
            <n-button :loading="ttsPreviewing" @click="previewTts">{{ t('setting.voicePreview') }}</n-button>
            <n-button @click="resetTts">{{ t('setting.ttsReset') }}</n-button>
            <n-button type="primary" :loading="ttsSaving" @click="saveTts">{{ t('setting.ttsSave') }}</n-button>
          </n-space>
        </n-form>
      </n-card>

      <!-- 版本更新:轻量提示(只告知 + 跳下载页,不做自动安装) -->
      <n-card :title="t('update.section')" class="setting-card">
        <n-form label-placement="top">
          <n-form-item :label="t('update.autoCheck')">
            <n-switch :value="autoCheck" @update:value="setAutoCheck" />
          </n-form-item>

          <n-form-item :label="t('update.currentVersion')">
            <span class="version-text">{{ currentVersion || '—' }}</span>
          </n-form-item>

          <n-space justify="end" align="center">
            <n-button v-if="latest" @click="openUpdateWindow">
              {{ t('update.viewNotes') }}
            </n-button>
            <n-button type="primary" :loading="checking" @click="handleCheckUpdate">
              {{ t('update.check') }}
            </n-button>
          </n-space>
        </n-form>
      </n-card>
    </div>

    <!-- 服务参数探测:把 OpenAPI 文档里的端点/字段/枚举摊给用户看,免得靠猜 -->
    <n-modal
      v-model:show="probeVisible"
      preset="card"
      :title="t('setting.probeTitle')"
      style="width: 760px; max-width: 94vw;"
    >
      <div v-if="probeResult" class="probe-body">
        <div class="probe-sec">
          <div class="probe-head">
            <span class="probe-label">{{ t('setting.probeSpec') }}</span>
            <span v-if="probeResult.spec?.found" class="probe-meta">
              {{ probeResult.spec.title }} · OpenAPI {{ probeResult.spec.version }}
            </span>
            <n-tag v-else size="small" type="warning">{{ t('setting.probeNotFound') }}</n-tag>
          </div>
          <div v-if="probeResult.spec?.found" class="probe-src">{{ probeResult.spec.url }}</div>
          <div v-if="probeResult.spec?.servers?.length" class="probe-src">
            servers: {{ probeResult.spec.servers.join(', ') }}
          </div>
          <div
            v-for="(ep, ei) in probeResult.spec?.endpoints || []"
            :key="ep.method + ep.path"
            class="probe-ep"
          >
            <div class="probe-ep-head">
              <n-tag size="small" :type="ep.method === 'POST' ? 'success' : 'default'">{{ ep.method }}</n-tag>
              <code class="probe-path">{{ ep.path }}</code>
              <span v-if="ep.summary" class="probe-summary">{{ ep.summary }}</span>
            </div>
            <div v-if="ep.params.length" class="probe-params">
              <span v-for="prm in ep.params" :key="prm.in + prm.name" class="probe-chip">
                [{{ prm.in }}] {{ prm.name }}<span v-if="prm.required" class="probe-star">*</span>
              </span>
            </div>
            <div v-if="ep.fields.length" class="probe-fields">
              <div v-for="f in ep.fields" :key="f.name" class="probe-field">
                <span class="probe-fname" :class="{ 'is-req': f.required }">{{ f.required ? '* ' : '' }}{{ f.name }}</span>
                <span class="probe-ftype">{{ f.type }}</span>
                <span v-if="f.enum" class="probe-fextra">enum: {{ f.enum.join(' | ') }}</span>
                <span v-if="f.default !== undefined" class="probe-fextra">default: {{ f.default }}</span>
              </div>
            </div>

            <!-- header/query 参数只做参考展示：真正填配置走下面的 curl 解析，避免两处都能填 -->
            <div v-if="ep.params.length" class="probe-fields">
              <div v-for="prm in ep.params" :key="prm.in + prm.name" class="probe-field">
                <span class="probe-fname" :class="{ 'is-req': prm.required }">
                  {{ prm.required ? '* ' : '' }}{{ prm.name }}
                </span>
                <span class="probe-ftype">{{ prm.in }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="probe-sec">
          <div class="probe-head">
            <span class="probe-label">{{ t('setting.probeVoices') }}</span>
            <span v-if="probeResult.voices?.found" class="probe-meta">
              {{ probeResult.voices.total }} · {{ probeResult.voices.url }}
            </span>
            <n-tag v-else size="small" type="warning">{{ t('setting.probeNotFound') }}</n-tag>
          </div>
          <div v-if="probeResult.voices?.found" class="probe-voices">
            <div v-for="v in probeResult.voices.items.slice(0, 30)" :key="v.id" class="probe-voice">
              <code class="probe-vid">{{ v.id }}</code>
              <span class="probe-vtitle">{{ v.title }}</span>
            </div>
          </div>
        </div>

        <n-collapse>
          <n-collapse-item :title="t('setting.probeTried')" name="tried">
            <div v-for="row in probeTried" :key="row.url" class="probe-tried">
              <span class="probe-tstatus">{{ row.status || 'ERR' }}</span>
              <span class="probe-turl">{{ row.url }}</span>
              <span v-if="row.note" class="probe-tnote">{{ row.note }}</span>
            </div>
          </n-collapse-item>
        </n-collapse>
      </div>
    </n-modal>

    <!-- 没有 API 文档时的兜底:把文档里那条能跑通的 curl 命令贴进来 -->
    <n-modal
      v-model:show="curlVisible"
      preset="card"
      :title="t('setting.curlTitle')"
      style="width: 700px; max-width: 94vw;"
    >
      <div class="probe-body">
        <div class="hint-text curl-hint">{{ t('setting.curlHint') }}</div>
        <n-input
          v-model:value="curlInput"
          type="textarea"
          :rows="6"
          :placeholder="CURL_PLACEHOLDER"
          class="curl-input"
        />
        <n-space justify="end" style="margin-top: 8px;">
          <n-button size="small" :loading="curlParsing" type="primary" @click="runParseCurl">
            {{ t('setting.curlParse') }}
          </n-button>
        </n-space>

        <div v-if="curlResult && curlResult.ok" class="curl-result">
          <div class="probe-ep-head">
            <n-tag size="small" type="success">{{ curlResult.method }}</n-tag>
            <code class="probe-path">{{ curlResult.url }}</code>
          </div>
          <div v-if="curlResult.content_type" class="probe-src">
            content-type: {{ curlResult.content_type }}
          </div>

          <div v-for="n in curlResult.notes || []" :key="n" class="curl-note">✓ {{ n }}</div>
          <div v-for="w in curlResult.warnings || []" :key="w" class="probe-src">⚠ {{ w }}</div>

          <!-- 解析结果本身就是一份能保存的配置，点一下直接写进表单，不用再手抄 -->
          <template v-if="curlConfig">
            <div class="probe-head" style="margin-top: 12px;">
              <span class="probe-label">{{ t('setting.curlWillApply') }}</span>
            </div>
            <div class="curl-apply">
              <div class="curl-apply-row">
                <span class="curl-apply-k">{{ t('setting.cloudBaseUrl') }}</span>
                <code class="curl-apply-v">{{ curlConfig.base_url || '—' }}</code>
              </div>
              <div class="curl-apply-row">
                <span class="curl-apply-k">{{ t('setting.cloudApiKey') }}</span>
                <code class="curl-apply-v">{{ curlConfig.api_key ? '******' : '—' }}</code>
              </div>
              <div class="curl-apply-row">
                <span class="curl-apply-k">{{ t('setting.cloudModel') }}</span>
                <code class="curl-apply-v">{{ curlConfig.model || '—' }}</code>
              </div>
              <div v-if="curlConfig.extra_headers" class="curl-apply-row is-block">
                <span class="curl-apply-k">{{ t('setting.extraHeaders') }}</span>
                <pre class="curl-apply-code">{{ curlConfig.extra_headers }}</pre>
              </div>
              <div v-if="curlConfig.body_template" class="curl-apply-row is-block">
                <span class="curl-apply-k">{{ t('setting.bodyTemplate') }}</span>
                <pre class="curl-apply-code">{{ curlConfig.body_template }}</pre>
              </div>
            </div>
            <n-space justify="end" style="margin-top: 8px;">
              <n-button size="small" type="primary" @click="applyCurlConfig">
                {{ t('setting.curlApply') }}
              </n-button>
            </n-space>
          </template>

          <n-collapse>
            <n-collapse-item :title="t('setting.curlRaw')" name="raw">
              <div v-if="curlHeaderRows.length" class="probe-fields">
                <div class="probe-head">
                  <span class="probe-label">{{ t('setting.curlHeaders') }}</span>
                </div>
                <div v-for="row in curlHeaderRows" :key="row.name" class="probe-field">
                  <span class="probe-fname">{{ row.name }}</span>
                  <span class="probe-ftype">{{ row.value }}</span>
                </div>
              </div>

              <div class="probe-head" style="margin-top: 12px;">
                <span class="probe-label">{{ t('setting.curlFields') }}</span>
              </div>
              <div v-if="curlResult.fields?.length" class="probe-fields">
                <div v-for="f in curlResult.fields" :key="f.name" class="probe-field">
                  <span class="probe-fname is-req">{{ f.name }}</span>
                  <span class="probe-ftype">{{ f.type }}</span>
                  <span class="probe-fextra">{{ f.sample }}</span>
                </div>
              </div>
              <div v-else class="probe-src">{{ t('setting.curlNoFields') }}</div>
            </n-collapse-item>
          </n-collapse>
        </div>
      </div>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
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
  probeVoiceApi,
  parseCurlApi,
  type VoiceConfigResp,
  type ProbeResult,
  type ProbeEndpoint,
  type CurlParseResult,
  BACKEND_URL,
} from '@/utils/backend'
import { useUpdateCheck } from '@/composables/useUpdateCheck'
import { openUpdateWindow } from '@/composables/useUpdateWindow'

const message = useMessage()
const { t } = useI18n()
const {
  currentVersion,
  latest,
  checking,
  error: updateError,
  autoCheck,
  setAutoCheck,
  initCurrentVersion,
  checkForUpdate,
  loadAutoCheck,
} = useUpdateCheck()

// 检查结果不占行内位置：已是最新/失败走 toast，有新版直接开独立更新窗口
async function handleCheckUpdate() {
  const result = await checkForUpdate({ manual: true })
  if (result === 'latest') message.success(t('update.upToDate'))
  else if (result === 'error') message.error(t('update.failed', { msg: updateError.value }))
}
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

/* ---------- 长任务:轮次上限 / 累积工具结果预算 ----------
 * 存后端 config/runtime_config.json,改完下一个请求就生效(不用重启 App)。 */
interface LongTaskPreset {
  mode: string
  max_tool_rounds: number
  max_cum_tool_tokens: number
}

const longTaskMode = ref('relaxed')
const longTaskLoading = ref(false)
const longTaskPresets = ref<LongTaskPreset[]>([])

const longTaskOptions = computed(() =>
  longTaskPresets.value.map((p) => ({
    label: t(`setting.longTaskMode_${p.mode}`),
    value: p.mode,
  })),
)

/** 提示行直接报当前档位的真实数字,避免「档位名和实际行为对不上」 */
const longTaskHint = computed(() => {
  const p = longTaskPresets.value.find((it) => it.mode === longTaskMode.value)
  if (!p) return t('setting.longTaskHintFallback')
  const rounds = p.max_tool_rounds
    ? String(p.max_tool_rounds)
    : t('setting.longTaskNoLimit')
  const tokens = p.max_cum_tool_tokens
    ? `${Math.round(p.max_cum_tool_tokens / 1000)}k`
    : t('setting.longTaskNoLimit')
  return t('setting.longTaskHint', { rounds, tokens })
})

async function loadLongTask() {
  try {
    const res = await fetch(`${BACKEND_URL}/settings/long-task`)
    if (!res.ok) return
    const data = await res.json()
    longTaskPresets.value = data.modes || []
    longTaskMode.value = data.config?.mode || 'relaxed'
  } catch (e) {
    console.debug('[setting] 读取长任务档位失败:', e)
  }
}

async function onLongTaskModeChange(mode: string) {
  longTaskLoading.value = true
  try {
    const res = await fetch(`${BACKEND_URL}/settings/long-task`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    message.success(t('setting.longTaskSaved'))
  } catch (e) {
    console.debug('[setting] 保存长任务档位失败:', e)
    message.error(t('setting.longTaskSaveFailed'))
    await loadLongTask()
  } finally {
    longTaskLoading.value = false
  }
}

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

async function testProactive() {
  const ok = await companion.testProactive()
  if (ok) {
    message.success(t('setting.companionProactiveTriggered'))
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
  openai_extra_headers: string
  openai_body_template: string
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
  return { enabled: true, priority0: 'edge', priority1: null, voice: '', speed: 1.0, openai_base_url: '', openai_api_key: '', openai_model: 'tts-1', openai_extra_headers: '', openai_body_template: '', custom_servers: '', edge_auto_update: true }
}

const sttForm = ref<SttSettings>(defaultStt())
const ttsForm = ref<TtsSettings>(defaultTts())
const notifyForm = ref<NotifySettings>({ ...defaultSettings })
const sttSaving = ref(false)
const ttsSaving = ref(false)
const ttsPreviewing = ref(false)

// 服务参数探测(只读 GET,不改配置):把服务到底要哪些字段摊给用户看
const ttsProbing = ref(false)
const probeVisible = ref(false)
const probeResult = ref<ProbeResult | null>(null)

/** spec 和 voices 各试了哪些地址,合成一份给「探测记录」用 */
const probeTried = computed(() => {
  const r = probeResult.value
  if (!r) return []
  return [...(r.spec?.tried || []), ...(r.voices?.tried || [])]
})

async function runTtsProbe() {
  const base = ttsForm.value.openai_base_url.trim()
  if (!base) {
    message.warning(t('setting.probeNoBase'))
    return
  }
  ttsProbing.value = true
  try {
    probeResult.value = await probeVoiceApi(base, ttsForm.value.openai_api_key)
    probeVisible.value = true
  } catch (e) {
    ;(window as any).$dialog?.error?.({
      title: t('setting.probeFail'),
      content: String((e as Error)?.message || e),
    })
  } finally {
    ttsProbing.value = false
  }
}


// 代码示例放在这里,不进 i18n:文案里的 `{` / `{{x}}` 会被 vue-i18n 当成
// 消息格式和插值语法,编译期就抛 SyntaxError,整个页面 render 直接崩
const CURL_PLACEHOLDER = `curl https://api.example.com/v1/tts \\
  -H "Authorization: Bearer xxx" \\
  -H "model: s2.1-pro-free" \\
  -d '{"text": "你好", "reference_id": "05ebc..."}'`
const EXTRA_HEADERS_PLACEHOLDER = `{
  "model": "s2.1-pro-free"
}`
const BODY_TEMPLATE_PLACEHOLDER = `{
  "text": {{text}},
  "reference_id": "05ebc5721353471f900561a781c96cd9",
  "prosody": { "speed": {{speed}} }
}`


// ---- 模型名的唯一入口:模型框 ----
// 同一个「模型名」在不同服务里位置不同（标准 OpenAI 在 body.model，fish 在 HTTP 请求头
// 的 model），只靠一个输入框很容易看不出它到底发在哪。所以模型框当唯一真相源：请求头
// 里已经有 model 键时，改模型框就自动跟过去，只动那一个键，其余头原样保留。
function headerModelKey(raw: string): string | null {
  const text = (raw || '').trim()
  if (!text) return null
  try {
    const obj = JSON.parse(text)
    if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return null
    return Object.keys(obj).find((k) => k.toLowerCase() === 'model') || null
  } catch {
    // 用户正在输入、JSON 还不完整 —— 不动它，免得把手打的内容冲掉
    return null
  }
}

/** 把模型框的值写回请求头里的 model 键（头里没有这个键就什么都不做） */
function syncModelToHeader(model: string) {
  const raw = ttsForm.value.openai_extra_headers
  const key = headerModelKey(raw)
  if (!key) return
  const obj = JSON.parse(raw)
  if (obj[key] === model) return
  obj[key] = model
  ttsForm.value.openai_extra_headers = JSON.stringify(obj, null, 2)
}

/** 模型名当前到底发在哪：body / header / 模板里固定 / 根本没发 */
type ModelPlacement = 'body' | 'header' | 'template' | 'unused'

const modelPlacement = computed<ModelPlacement>(() => {
  const tpl = (ttsForm.value.openai_body_template || '').trim()
  // 模板里有占位符，不能 JSON.parse，直接认字面量
  if (tpl && /"model"\s*:/i.test(tpl)) return 'template'
  if (headerModelKey(ttsForm.value.openai_extra_headers)) return 'header'
  if (!tpl) return 'body'
  return 'unused'
})

const MODEL_HINT_KEYS = {
  body: 'setting.modelPlacementBody',
  header: 'setting.modelPlacementHeader',
  template: 'setting.modelPlacementTemplate',
  unused: 'setting.modelPlacementUnused',
} as const

const modelHint = computed(() => t(MODEL_HINT_KEYS[modelPlacement.value]))
// 后两种是「模型框不生效」，得显眼一点
const modelHintWarn = computed(
  () => modelPlacement.value === 'template' || modelPlacement.value === 'unused',
)

watch(() => ttsForm.value.openai_model, (v) => syncModelToHeader(v))

// ---- curl 兑底:没有 API 文档的服务,从文档里那条能跑通的命令反解 ----
const curlVisible = ref(false)
const curlInput = ref('')
const curlParsing = ref(false)
const curlResult = ref<CurlParseResult | null>(null)

/** 后端算好的配置:点一下直接写进表单 */
const curlConfig = computed(() => curlResult.value?.config || null)

/** header 转成列表渲染(对象在模板里直接 v-for 不好按 key 排序) */
const curlHeaderRows = computed(() =>
  Object.entries(curlResult.value?.headers || {}).map(([name, value]) => ({ name, value })),
)

function applyCurlConfig() {
  const c = curlConfig.value
  if (!c) return
  if (c.base_url) ttsForm.value.openai_base_url = c.base_url
  if (c.api_key) ttsForm.value.openai_api_key = c.api_key
  // 先写 model 再写请求头:写 model 会触发自动同步，后面的头才是最终结果
  if (c.model) ttsForm.value.openai_model = c.model
  ttsForm.value.openai_extra_headers = c.extra_headers || ''
  ttsForm.value.openai_body_template = c.body_template || ''
  curlVisible.value = false
  message.success(t('setting.curlApplied'))
}

async function runParseCurl() {
  const cmd = curlInput.value.trim()
  if (!cmd) {
    message.warning(t('setting.curlEmpty'))
    return
  }
  curlParsing.value = true
  try {
    curlResult.value = await parseCurlApi(cmd)
    if (curlResult.value.ok === false) {
      message.error(`${t('setting.curlFail')}: ${curlResult.value.error || ''}`)
    }
  } catch (e) {
    ;(window as any).$dialog?.error?.({
      title: t('setting.curlFail'),
      content: String((e as Error)?.message || e),
    })
  } finally {
    curlParsing.value = false
  }
}

// edge-tts 的 403 自愈(升库 + 重试一次)现在恒开启，不再给用户开关/手动升级入口

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
// 主/备引擎下拉:云端引擎的可用性还要看「当前表单填了什么」——
// 用户刚填完 base_url/key 还没保存时,后端 status 里仍是不可用,
// 选项会变灰 → 选不了引擎就无从试听。这里按后端 available() 的口径
// (openai: 填了 base_url 或 key;custom: 填了任意一个地址)本地救活。
function engineFilled(name: string): boolean {
  const f = ttsForm.value
  if (name === 'openai') return !!(f.openai_base_url.trim() || f.openai_api_key.trim())
  if (name === 'custom') return !!f.custom_servers.trim()
  return false
}
const ttsPrimaryOptions = computed(() =>
  Object.entries(ttsStatus.value).map(([name, info]) => {
    const avail = info.available || engineFilled(name)
    return {
      label: `${TTS_ENGINE_LABELS[name] || name} — ${avail ? t('setting.voiceEngineAvail') : t('setting.voiceEngineUnavail')}`,
      value: name,
      disabled: !avail,
    }
  }),
)
const ttsSecondaryOptions = computed(() =>
  Object.entries(ttsStatus.value)
    .filter(([name]) => name !== ttsForm.value.priority0)
    .map(([name, info]) => {
      const avail = info.available || engineFilled(name)
      return {
        label: `${TTS_ENGINE_LABELS[name] || name} — ${avail ? t('setting.voiceEngineAvail') : t('setting.voiceEngineUnavail')}`,
        value: name,
        disabled: !avail,
      }
    }),
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
      openai_extra_headers: (tts as any).openai_extra_headers || '',
      openai_body_template: (tts as any).openai_body_template || '',
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
  void loadLongTask()
  // 版本信息(含自动检查开关)；不在这里主动检查，避免进设置页就发请求
  void initCurrentVersion()
  loadAutoCheck()
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
  patch.openai_extra_headers = f.openai_extra_headers.trim()
  patch.openai_body_template = f.openai_body_template.trim()
  patch.custom_servers = f.custom_servers
  // edge_auto_update 已从 UI 移除并在后端恒开启,不再回传
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
    // 只试听当前主引擎:云端配错时直接报错,而不是静默降级到备引擎
    // (否则听到的是备引擎的声音,却以为云端已经配通了)
    const url = await previewTtsApi(
      t('setting.voicePreviewText'),
      ttsForm.value.speed,
      ttsForm.value.priority0,
    )
    if (ttsAudio) { ttsAudio.pause(); ttsAudio = null }
    ttsAudio = new Audio(url)
    // ended / error 都要回收,否则 blob URL 会一直挂着
    ttsAudio.onended = () => { URL.revokeObjectURL(url) }
    ttsAudio.onerror = () => { URL.revokeObjectURL(url) }
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

/* 模型框下方那行：模型当前到底发在哪。模板里已固定/完全没发时提醒一下 */
.hint-text.is-warn {
  color: var(--warning);
}

/* 用 OpenAI 兼容引擎时音色项换成这行说明，保持和 form-item 一致的段落间距 */
.tts-voice-note {
  margin-bottom: 18px;
}

/* curl 解析出的「将要填入」配置预览 */
.curl-note {
  font-size: 12px;
  line-height: 1.7;
  color: var(--success);
}

.curl-apply {
  margin-top: 6px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
}

.curl-apply-row {
  display: flex;
  gap: 8px;
  align-items: baseline;
  font-size: 12px;
  line-height: 1.8;
}

.curl-apply-row.is-block {
  flex-direction: column;
  gap: 2px;
  margin-top: 6px;
}

.curl-apply-k {
  flex: none;
  min-width: 96px;
  color: var(--text-muted);
}

.curl-apply-v {
  word-break: break-all;
}

.curl-apply-code {
  margin: 0;
  padding: 6px 8px;
  max-height: 160px;
  overflow: auto;
  border-radius: 4px;
  background: var(--bg-app);
  font-size: 11px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
}

/* 试听按钮上方的说明:强调不降级,失败就是主引擎的真失败 */
.tts-preview-hint {
  text-align: right;
  margin-bottom: 6px;
}

/* ---- 服务参数探测弹窗 ---- */
.probe-body {
  max-height: 66vh;
  overflow-y: auto;
}

.probe-sec {
  margin-bottom: 16px;
}

.probe-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}

.probe-label {
  font-weight: 600;
  color: var(--text-primary);
}

.probe-meta {
  font-size: 12px;
  color: var(--text-muted);
  word-break: break-all;
}

.probe-src {
  font-size: 12px;
  color: var(--text-muted);
  word-break: break-all;
  margin-bottom: 4px;
}

.probe-ep {
  border-left: 2px solid var(--border);
  padding-left: 10px;
  margin: 10px 0;
}

.probe-ep-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.probe-path {
  font-family: var(--font-mono);
  font-size: 13px;
}

.probe-summary {
  font-size: 12px;
  color: var(--text-muted);
}

.probe-params {
  margin-top: 4px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.probe-chip {
  font-size: 12px;
  font-family: var(--font-mono);
  background: var(--surface-hover);
  border-radius: var(--radius-sm);
  padding: 1px 6px;
}

.probe-star {
  color: var(--error);
}

.probe-fields {
  margin-top: 4px;
}

.probe-field {
  display: flex;
  gap: 10px;
  align-items: baseline;
  font-size: 12px;
  padding: 1px 0;
}

.probe-fname {
  font-family: var(--font-mono);
  min-width: 150px;
}

.probe-fname.is-req {
  color: var(--error);
}

.probe-ftype {
  color: var(--text-muted);
  min-width: 80px;
}

.probe-fextra {
  color: var(--text-muted);
}

.probe-voices {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 180px;
  overflow-y: auto;
}

.probe-voice {
  display: flex;
  gap: 10px;
  font-size: 12px;
}

.probe-vid {
  font-family: var(--font-mono);
  color: var(--text-muted);
  flex-shrink: 0;
}

.probe-tried {
  display: flex;
  gap: 8px;
  font-size: 12px;
  padding: 1px 0;
}

.probe-tstatus {
  font-family: var(--font-mono);
  min-width: 34px;
  color: var(--text-muted);
}

.probe-turl {
  font-family: var(--font-mono);
  word-break: break-all;
}

.probe-tnote {
  color: var(--text-muted);
}

/* ---- curl 解析 ---- */
.curl-hint {
  margin-bottom: 8px;
}

.curl-input :deep(textarea) {
  font-family: var(--font-mono);
  font-size: 12px;
}

.curl-result {
  margin-top: 14px;
  border-top: 1px solid var(--border);
  padding-top: 12px;
}

/* 自定义请求头 / body 模板:JSON 用等宽字体,写错一眼能看出来 */
.json-input :deep(textarea) {
  font-family: var(--font-mono);
  font-size: 12px;
}

/* ---- 探测结果 → 实时表单 ---- */
.probe-form-actions {
  margin-top: 6px;
}

.probe-form {
  margin-top: 8px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  background: var(--bg-surface);
}

.pf-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}

.pf-row.is-sub {
  padding-left: 14px;
}

.pf-label {
  min-width: 170px;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-primary);
  flex-shrink: 0;
}

.pf-label.is-req {
  color: var(--error);
}

.pf-in {
  font-style: normal;
  font-size: 11px;
  color: var(--text-muted);
}

.pf-ctl {
  flex: 1;
  min-width: 0;
}

.pf-desc {
  font-size: 11px;
  color: var(--text-muted);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pf-foot {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
}

/* 版本号：比正文大一级、等宽字体，不用 tag 以免看着像可选状态 */
.version-text {
  font-family: var(--font-mono);
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--text-primary);
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
