<template>
  <div class="setting-page">
    <TitleBar />
    <div class="setting-card-wrapper">
      <n-card :title="t('modelSetting.title')" class="setting-card">
        <template #header-extra>
          <n-button circle text @click="router.back()">
            <template #icon>
              <span style="font-size: 18px; font-weight: bold;">✕</span>
            </template>
          </n-button>
        </template>

        <div class="scrollable-form">
          <n-form :model="form" label-placement="top">
            <div class="form-section">
              <n-form-item :label="t('modelSetting.provider')" style="padding:10px">
                <div class="provider-grid">
                  <div
                    v-for="p in providers"
                    :key="p.id"
                    class="provider-card"
                    :class="{ active: selectedProvider === p.id }"
                    @click="selectProvider(p)"
                  >
                    <span class="provider-icon" v-html="p.icon"></span>
                    <span class="provider-name">{{ p.name }}</span>
                  </div>
                </div>
              </n-form-item>
            </div>

            <div class="form-section">
              <n-form-item :label="t('modelSetting.apiKey')">
                <n-input
                  v-model:value="form.apiKey"
                  type="password"
                  show-password-on="click"
                  :placeholder="t('modelSetting.apiKeyPlaceholder')"
                />
              </n-form-item>
            </div>
            <div class="form-section">
              <n-form-item :label="t('modelSetting.baseUrl')" v-if="selectedProvider === 'custom' || currentProviderNeedsBase">
                <n-input
                  v-model:value="form.baseUrl"
                  :placeholder="selectedProvider === 'custom' ? t('modelSetting.baseUrlPlaceholder') : t('modelSetting.baseUrlOptional')"
                />
              </n-form-item>
            </div>
            <div class="form-section">
              <n-form-item :label="t('modelSetting.model')">
                <n-input-group>
                  <n-select
                    v-model:value="form.model"
                    :options="modelOptions"
                    filterable
                    tag
                    :placeholder="t('modelSetting.modelPlaceholder')"
                    style="flex: 1"
                  />
                  <n-button
                    v-if="selectedProvider === 'custom'"
                    :loading="fetchingModels"
                    @click="handleFetchModels"
                    style="width: 110px; flex-shrink: 0;"
                  >
                    {{ fetchingModels ? t('modelSetting.fetching') : t('modelSetting.fetchModels') }}
                  </n-button>
                </n-input-group>
              </n-form-item>
            </div>

            <div class="form-section">
              <n-form-item :label="t('modelSetting.subAgentModel')">
                <div class="field-stack">
                  <n-input-group>
                    <n-select
                      v-model:value="form.subModel"
                      :options="subModelOptions"
                      filterable
                      tag
                      clearable
                      :placeholder="t('modelSetting.subAgentModelPlaceholder')"
                      style="flex: 1"
                    />
                    <n-button
                      v-if="selectedProvider === 'custom'"
                      :loading="fetchingModels"
                      @click="handleFetchModels"
                      style="width: 110px; flex-shrink: 0;"
                    >
                      {{ fetchingModels ? t('modelSetting.fetching') : t('modelSetting.fetchModels') }}
                    </n-button>
                  </n-input-group>
                  <div class="field-hint">{{ t('modelSetting.subAgentModelHint') }}</div>
                </div>
              </n-form-item>
            </div>

            <div class="form-section">
              <n-form-item :label="t('modelSetting.systemPrompt')">
                <div class="field-stack">
                  <n-input
                    v-model:value="form.systemPrompt"
                    type="textarea"
                    :autosize="{ minRows: 3, maxRows: 8 }"
                    :placeholder="t('modelSetting.systemPromptPlaceholder')"
                  />
                  <div class="preset-tags">
                    <span class="preset-label">{{ t('modelSetting.presetLabel') }}</span>
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
                </div>
              </n-form-item>
            </div>

            <n-space justify="end" style="margin-top: 8px; padding-top: 12px; border-top: 1px solid var(--border);">
              <n-button @click="handleReset">{{ t('modelSetting.reset') }}</n-button>
              <n-button :loading="testing" @click="handleTest">{{ t('modelSetting.test') }}</n-button>
              <n-button type="primary" @click="handleSave">{{ t('modelSetting.save') }}</n-button>
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
import { useI18n } from 'vue-i18n'
import TitleBar from '@/components/TitleBar.vue'
import { useSettings } from '@/composables/useSettings'
import { useApiClient } from '@/composables/useApiClient'
const router = useRouter()
const message = useMessage()
const { t } = useI18n()
const { settings, loadSettings, saveSettings, resetSettings } = useSettings()
const { fetchModels, testConnection } = useApiClient()

interface Provider {
  id: string
  name: string
  icon: string
  baseUrl: string        
  needsBase: boolean    
  models: string[]       
}

// 简洁单色 SVG 图标（currentColor，随卡片选中态变色）
const ICONS = {
  openai: '<svg fill="white" fill-rule="evenodd" height="40" style="flex: 0 0 auto; line-height: 1;" viewBox="0 0 24 24" width="40" xmlns="http://www.w3.org/2000/svg"><title>OpenAI</title><path d="M9.205 8.658v-2.26c0-.19.072-.333.238-.428l4.543-2.616c.619-.357 1.356-.523 2.117-.523 2.854 0 4.662 2.212 4.662 4.566 0 .167 0 .357-.024.547l-4.71-2.759a.797.797 0 00-.856 0l-5.97 3.473zm10.609 8.8V12.06c0-.333-.143-.57-.429-.737l-5.97-3.473 1.95-1.118a.433.433 0 01.476 0l4.543 2.617c1.309.76 2.189 2.378 2.189 3.948 0 1.808-1.07 3.473-2.76 4.163zM7.802 12.703l-1.95-1.142c-.167-.095-.239-.238-.239-.428V5.899c0-2.545 1.95-4.472 4.591-4.472 1 0 1.927.333 2.712.928L8.23 5.067c-.285.166-.428.404-.428.737v6.898zM12 15.128l-2.795-1.57v-3.33L12 8.658l2.795 1.57v3.33L12 15.128zm1.796 7.23c-1 0-1.927-.332-2.712-.927l4.686-2.712c.285-.166.428-.404.428-.737v-6.898l1.974 1.142c.167.095.238.238.238.428v5.233c0 2.545-1.974 4.472-4.614 4.472zm-5.637-5.303l-4.544-2.617c-1.308-.761-2.188-2.378-2.188-3.948A4.482 4.482 0 014.21 6.327v5.423c0 .333.143.571.428.738l5.947 3.449-1.95 1.118a.432.432 0 01-.476 0zm-.262 3.9c-2.688 0-4.662-2.021-4.662-4.519 0-.19.024-.38.047-.57l4.686 2.71c.286.167.571.167.856 0l5.97-3.448v2.26c0 .19-.07.333-.237.428l-4.543 2.616c-.619.357-1.356.523-2.117.523zm5.899 2.83a5.947 5.947 0 005.827-4.756C22.287 18.339 24 15.84 24 13.296c0-1.665-.713-3.282-1.998-4.448.119-.5.19-.999.19-1.498 0-3.401-2.759-5.947-5.946-5.947-.642 0-1.26.095-1.88.31A5.962 5.962 0 0010.205 0a5.947 5.947 0 00-5.827 4.757C1.713 5.447 0 7.945 0 10.49c0 1.666.713 3.283 1.998 4.448-.119.5-.19 1-.19 1.499 0 3.401 2.759 5.946 5.946 5.946.642 0 1.26-.095 1.88-.309a5.96 5.96 0 004.162 1.713z"></path></svg>',
  anthropic: `<svg height="40" style="flex: 0 0 auto; line-height: 1;" viewBox="0 0 24 24" width="40" xmlns="http://www.w3.org/2000/svg"><title>Claude</title><path d="M4.709 15.955l4.72-2.647.08-.23-.08-.128H9.2l-.79-.048-2.698-.073-2.339-.097-2.266-.122-.571-.121L0 11.784l.055-.352.48-.321.686.06 1.52.103 2.278.158 1.652.097 2.449.255h.389l.055-.157-.134-.098-.103-.097-2.358-1.596-2.552-1.688-1.336-.972-.724-.491-.364-.462-.158-1.008.656-.722.881.06.225.061.893.686 1.908 1.476 2.491 1.833.365.304.145-.103.019-.073-.164-.274-1.355-2.446-1.446-2.49-.644-1.032-.17-.619a2.97 2.97 0 01-.104-.729L6.283.134 6.696 0l.996.134.42.364.62 1.414 1.002 2.229 1.555 3.03.456.898.243.832.091.255h.158V9.01l.128-1.706.237-2.095.23-2.695.08-.76.376-.91.747-.492.584.28.48.685-.067.444-.286 1.851-.559 2.903-.364 1.942h.212l.243-.242.985-1.306 1.652-2.064.73-.82.85-.904.547-.431h1.033l.76 1.129-.34 1.166-1.064 1.347-.881 1.142-1.264 1.7-.79 1.36.073.11.188-.02 2.856-.606 1.543-.28 1.841-.315.833.388.091.395-.328.807-1.969.486-2.309.462-3.439.813-.042.03.049.061 1.549.146.662.036h1.622l3.02.225.79.522.474.638-.079.485-1.215.62-1.64-.389-3.829-.91-1.312-.329h-.182v.11l1.093 1.068 2.006 1.81 2.509 2.33.127.578-.322.455-.34-.049-2.205-1.657-.851-.747-1.926-1.62h-.128v.17l.444.649 2.345 3.521.122 1.08-.17.353-.608.213-.668-.122-1.374-1.925-1.415-2.167-1.143-1.943-.14.08-.674 7.254-.316.37-.729.28-.607-.461-.322-.747.322-1.476.389-1.924.315-1.53.286-1.9.17-.632-.012-.042-.14.018-1.434 1.967-2.18 2.945-1.726 1.845-.414.164-.717-.37.067-.662.401-.589 2.388-3.036 1.44-1.882.93-1.086-.006-.158h-.055L4.132 18.56l-1.13.146-.487-.456.061-.746.231-.243 1.908-1.312-.006.006z" fill="#D97757" fill-rule="nonzero"></path></svg>`,
  google: `<svg height="40" style="flex: 0 0 auto; line-height: 1;" viewBox="0 0 24 24" width="40" xmlns="http://www.w3.org/2000/svg"><title>Gemini</title><path d="M20.616 10.835a14.147 14.147 0 01-4.45-3.001 14.111 14.111 0 01-3.678-6.452.503.503 0 00-.975 0 14.134 14.134 0 01-3.679 6.452 14.155 14.155 0 01-4.45 3.001c-.65.28-1.318.505-2.002.678a.502.502 0 000 .975c.684.172 1.35.397 2.002.677a14.147 14.147 0 014.45 3.001 14.112 14.112 0 013.679 6.453.502.502 0 00.975 0c.172-.685.397-1.351.677-2.003a14.145 14.145 0 013.001-4.45 14.113 14.113 0 016.453-3.678.503.503 0 000-.975 13.245 13.245 0 01-2.003-.678z" fill="#3186FF"></path><path d="M20.616 10.835a14.147 14.147 0 01-4.45-3.001 14.111 14.111 0 01-3.678-6.452.503.503 0 00-.975 0 14.134 14.134 0 01-3.679 6.452 14.155 14.155 0 01-4.45 3.001c-.65.28-1.318.505-2.002.678a.502.502 0 000 .975c.684.172 1.35.397 2.002.677a14.147 14.147 0 014.45 3.001 14.112 14.112 0 013.679 6.453.502.502 0 00.975 0c.172-.685.397-1.351.677-2.003a14.145 14.145 0 013.001-4.45 14.113 14.113 0 016.453-3.678.503.503 0 000-.975 13.245 13.245 0 01-2.003-.678z" fill="url(#lobe-icons-gemini-0-_r_g_)"></path><path d="M20.616 10.835a14.147 14.147 0 01-4.45-3.001 14.111 14.111 0 01-3.678-6.452.503.503 0 00-.975 0 14.134 14.134 0 01-3.679 6.452 14.155 14.155 0 01-4.45 3.001c-.65.28-1.318.505-2.002.678a.502.502 0 000 .975c.684.172 1.35.397 2.002.677a14.147 14.147 0 014.45 3.001 14.112 14.112 0 013.679 6.453.502.502 0 00.975 0c.172-.685.397-1.351.677-2.003a14.145 14.145 0 013.001-4.45 14.113 14.113 0 016.453-3.678.503.503 0 000-.975 13.245 13.245 0 01-2.003-.678z" fill="url(#lobe-icons-gemini-1-_r_g_)"></path><path d="M20.616 10.835a14.147 14.147 0 01-4.45-3.001 14.111 14.111 0 01-3.678-6.452.503.503 0 00-.975 0 14.134 14.134 0 01-3.679 6.452 14.155 14.155 0 01-4.45 3.001c-.65.28-1.318.505-2.002.678a.502.502 0 000 .975c.684.172 1.35.397 2.002.677a14.147 14.147 0 014.45 3.001 14.112 14.112 0 013.679 6.453.502.502 0 00.975 0c.172-.685.397-1.351.677-2.003a14.145 14.145 0 013.001-4.45 14.113 14.113 0 016.453-3.678.503.503 0 000-.975 13.245 13.245 0 01-2.003-.678z" fill="url(#lobe-icons-gemini-2-_r_g_)"></path><defs><linearGradient gradientUnits="userSpaceOnUse" id="lobe-icons-gemini-0-_r_g_" x1="7" x2="11" y1="15.5" y2="12"><stop stop-color="#08B962"></stop><stop offset="1" stop-color="#08B962" stop-opacity="0"></stop></linearGradient><linearGradient gradientUnits="userSpaceOnUse" id="lobe-icons-gemini-1-_r_g_" x1="8" x2="11.5" y1="5.5" y2="11"><stop stop-color="#F94543"></stop><stop offset="1" stop-color="#F94543" stop-opacity="0"></stop></linearGradient><linearGradient gradientUnits="userSpaceOnUse" id="lobe-icons-gemini-2-_r_g_" x1="3.5" x2="17.5" y1="13.5" y2="12"><stop stop-color="#FABC12"></stop><stop offset=".46" stop-color="#FABC12" stop-opacity="0"></stop></linearGradient></defs></svg>`,
  deepseek: `<svg height="40" style="flex: 0 0 auto; line-height: 1;" viewBox="0 0 24 24" width="40" xmlns="http://www.w3.org/2000/svg"><title>DeepSeek</title><path d="M23.748 4.482c-.254-.124-.364.113-.512.234-.051.039-.094.09-.137.136-.372.397-.806.657-1.373.626-.829-.046-1.537.214-2.163.848-.133-.782-.575-1.248-1.247-1.548-.352-.156-.708-.311-.955-.65-.172-.241-.219-.51-.305-.774-.055-.16-.11-.323-.293-.35-.2-.031-.278.136-.356.276-.313.572-.434 1.202-.422 1.84.027 1.436.633 2.58 1.838 3.393.137.093.172.187.129.323-.082.28-.18.552-.266.833-.055.179-.137.217-.329.14a5.526 5.526 0 01-1.736-1.18c-.857-.828-1.631-1.742-2.597-2.458a11.365 11.365 0 00-.689-.471c-.985-.957.13-1.743.388-1.836.27-.098.093-.432-.779-.428-.872.004-1.67.295-2.687.684a3.055 3.055 0 01-.465.137 9.597 9.597 0 00-2.883-.102c-1.885.21-3.39 1.102-4.497 2.623C.082 8.606-.231 10.684.152 12.85c.403 2.284 1.569 4.175 3.36 5.653 1.858 1.533 3.997 2.284 6.438 2.14 1.482-.085 3.133-.284 4.994-1.86.47.234.962.327 1.78.397.63.059 1.236-.03 1.705-.128.735-.156.684-.837.419-.961-2.155-1.004-1.682-.595-2.113-.926 1.096-1.296 2.746-2.642 3.392-7.003.05-.347.007-.565 0-.845-.004-.17.035-.237.23-.256a4.173 4.173 0 001.545-.475c1.396-.763 1.96-2.015 2.093-3.517.02-.23-.004-.467-.247-.588zM11.581 18c-2.089-1.642-3.102-2.183-3.52-2.16-.392.024-.321.471-.235.763.09.288.207.486.371.739.114.167.192.416-.113.603-.673.416-1.842-.14-1.897-.167-1.361-.802-2.5-1.86-3.301-3.307-.774-1.393-1.224-2.887-1.298-4.482-.02-.386.093-.522.477-.592a4.696 4.696 0 011.529-.039c2.132.312 3.946 1.265 5.468 2.774.868.86 1.525 1.887 2.202 2.891.72 1.066 1.494 2.082 2.48 2.914.348.292.625.514.891.677-.802.09-2.14.11-3.054-.614zm1-6.44a.306.306 0 01.415-.287.302.302 0 01.2.288.306.306 0 01-.31.307.303.303 0 01-.304-.308zm3.11 1.596c-.2.081-.399.151-.59.16a1.245 1.245 0 01-.798-.254c-.274-.23-.47-.358-.552-.758a1.73 1.73 0 01.016-.588c.07-.327-.008-.537-.239-.727-.187-.156-.426-.199-.688-.199a.559.559 0 01-.254-.078c-.11-.054-.2-.19-.114-.358.028-.054.16-.186.192-.21.356-.202.767-.136 1.146.016.352.144.618.408 1.001.782.391.451.462.576.685.914.176.265.336.537.445.848.067.195-.019.354-.25.452z" fill="#4D6BFE"></path></svg>`,
  mistral: `<svg viewBox="0 0 21 15" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M6 0H3V3H6V0Z" fill="#FFAF01" style="--darkreader-inline-fill: var(--darkreader-text-ffaf01, #ffb71a);" data-darkreader-inline-fill=""></path>
<path d="M6 9H3V12H6V9Z" fill="#E61300" style="--darkreader-inline-fill: var(--darkreader-text-e61300, #ff3d2b);" data-darkreader-inline-fill=""></path>
<path d="M9 12H0V15H9V12Z" fill="#C4001D" style="--darkreader-inline-fill: var(--darkreader-text-c4001d, #ff435f);" data-darkreader-inline-fill=""></path>
<path d="M9 3H3V6H9V3Z" fill="#FF8204" style="--darkreader-inline-fill: var(--darkreader-text-ff8204, #ff8e1c);" data-darkreader-inline-fill=""></path>
<path d="M12 9H9V12H12V9Z" fill="#E61300" style="--darkreader-inline-fill: var(--darkreader-text-e61300, #ff3d2b);" data-darkreader-inline-fill=""></path>
<path d="M18 6H3V9H18V6Z" fill="#FA500F" style="--darkreader-inline-fill: var(--darkreader-text-fa500f, #fa6025);" data-darkreader-inline-fill=""></path>
<path d="M18 3H12V6H18V3Z" fill="#FF8204" style="--darkreader-inline-fill: var(--darkreader-text-ff8204, #ff8e1c);" data-darkreader-inline-fill=""></path>
<path d="M18 0H15V3H18V0Z" fill="#FFAF01" style="--darkreader-inline-fill: var(--darkreader-text-ffaf01, #ffb71a);" data-darkreader-inline-fill=""></path>
<path d="M18 9H15V12H18V9Z" fill="#E61300" style="--darkreader-inline-fill: var(--darkreader-text-e61300, #ff3d2b);" data-darkreader-inline-fill=""></path>
<path d="M21 12H12V15H21V12Z" fill="#C4001D" style="--darkreader-inline-fill: var(--darkreader-text-c4001d, #ff435f);" data-darkreader-inline-fill=""></path>
</svg>`,
  kimi: `<svg fill="white" fill-rule="evenodd" height="40" style="flex: 0 0 auto; line-height: 1;" viewBox="0 0 24 24" width="40" xmlns="http://www.w3.org/2000/svg"><title>MoonshotAI</title><path d="M1.052 16.916l9.539 2.552a21.007 21.007 0 00.06 2.033l5.956 1.593a11.997 11.997 0 01-5.586.865l-.18-.016-.044-.004-.084-.009-.094-.01a11.605 11.605 0 01-.157-.02l-.107-.014-.11-.016a11.962 11.962 0 01-.32-.051l-.042-.008-.075-.013-.107-.02-.07-.015-.093-.019-.075-.016-.095-.02-.097-.023-.094-.022-.068-.017-.088-.022-.09-.024-.095-.025-.082-.023-.109-.03-.062-.02-.084-.025-.093-.028-.105-.034-.058-.019-.08-.026-.09-.031-.066-.024a6.293 6.293 0 01-.044-.015l-.068-.025-.101-.037-.057-.022-.08-.03-.087-.035-.088-.035-.079-.032-.095-.04-.063-.028-.063-.027a5.655 5.655 0 01-.041-.018l-.066-.03-.103-.047-.052-.024-.096-.046-.062-.03-.084-.04-.086-.044-.093-.047-.052-.027-.103-.055-.057-.03-.058-.032a6.49 6.49 0 01-.046-.026l-.094-.053-.06-.034-.051-.03-.072-.041-.082-.05-.093-.056-.052-.032-.084-.053-.061-.039-.079-.05-.07-.047-.053-.035a7.785 7.785 0 01-.054-.036l-.044-.03-.044-.03a6.066 6.066 0 01-.04-.028l-.057-.04-.076-.054-.069-.05-.074-.054-.056-.042-.076-.057-.076-.059-.086-.067-.045-.035-.064-.052-.074-.06-.089-.073-.046-.039-.046-.039a7.516 7.516 0 01-.043-.037l-.045-.04-.061-.053-.07-.062-.068-.06-.062-.058-.067-.062-.053-.05-.088-.084a13.28 13.28 0 01-.099-.097l-.029-.028-.041-.042-.069-.07-.05-.051-.05-.053a6.457 6.457 0 01-.168-.179l-.08-.088-.062-.07-.071-.08-.042-.049-.053-.062-.058-.068-.046-.056a7.175 7.175 0 01-.027-.033l-.045-.055-.066-.082-.041-.052-.05-.064-.02-.025a11.99 11.99 0 01-1.44-2.402zm-1.02-5.794l11.353 3.037a20.468 20.468 0 00-.469 2.011l10.817 2.894a12.076 12.076 0 01-1.845 2.005L.657 15.923l-.016-.046-.035-.104a11.965 11.965 0 01-.05-.153l-.007-.023a11.896 11.896 0 01-.207-.741l-.03-.126-.018-.08-.021-.097-.018-.081-.018-.09-.017-.084-.018-.094c-.026-.141-.05-.283-.071-.426l-.017-.118-.011-.083-.013-.102a12.01 12.01 0 01-.019-.161l-.005-.047a12.12 12.12 0 01-.034-2.145zm1.593-5.15l11.948 3.196c-.368.605-.705 1.231-1.01 1.875l11.295 3.022c-.142.82-.368 1.612-.668 2.365l-11.55-3.09L.124 10.26l.015-.1.008-.049.01-.067.015-.087.018-.098c.026-.148.056-.295.088-.442l.028-.124.02-.085.024-.097c.022-.09.045-.18.07-.268l.028-.102.023-.083.03-.1.025-.082.03-.096.026-.082.031-.095a11.896 11.896 0 011.01-2.232zm4.442-4.4L17.352 4.59a20.77 20.77 0 00-1.688 1.721l7.823 2.093c.267.852.442 1.744.513 2.665L2.106 5.213l.045-.065.027-.04.04-.055.046-.065.055-.076.054-.072.064-.086.05-.065.057-.073.055-.07.06-.074.055-.069.065-.077.054-.066.066-.077.053-.06.072-.082.053-.06.067-.074.054-.058.073-.078.058-.06.063-.067.168-.17.1-.098.059-.056.076-.071a12.084 12.084 0 012.272-1.677zM12.017 0h.097l.082.001.069.001.054.002.068.002.046.001.076.003.047.002.06.003.054.002.087.005.105.007.144.011.088.007.044.004.077.008.082.008.047.005.102.012.05.006.108.014.081.01.042.006.065.01.207.032.07.012.065.011.14.026.092.018.11.022.046.01.075.016.041.01L14.7.3l.042.01.065.015.049.012.071.017.096.024.112.03.113.03.113.032.05.015.07.02.078.024.073.023.05.016.05.016.076.025.099.033.102.036.048.017.064.023.093.034.11.041.116.045.1.04.047.02.06.024.041.018.063.026.04.018.057.025.11.048.1.046.074.035.075.036.06.028.092.046.091.045.102.052.053.028.049.026.046.024.06.033.041.022.052.029.088.05.106.06.087.051.057.034.053.032.096.059.088.055.098.062.036.024.064.041.084.056.04.027.062.042.062.043.023.017c.054.037.108.075.161.114l.083.06.065.048.056.043.086.065.082.064.04.03.05.041.086.069.079.065.085.071c.712.6 1.353 1.283 1.909 2.031L7.222.994l.062-.027.065-.028.081-.034.086-.035c.113-.045.227-.09.341-.131l.096-.035.093-.033.084-.03.096-.031c.087-.03.176-.058.264-.085l.091-.027.086-.025.102-.03.085-.023.1-.026L9.04.37l.09-.023.091-.022.095-.022.09-.02.098-.021.091-.02.095-.018.092-.018.1-.018.091-.016.098-.017.092-.014.097-.015.092-.013.102-.013.091-.012.105-.012.09-.01.105-.01c.093-.01.186-.018.28-.024l.106-.008.09-.005.11-.006.093-.004.1-.004.097-.002.099-.002.197-.002z"></path></svg>`,
  grok: `<svg fill="white" fill-rule="evenodd" height="40" style="flex: 0 0 auto; line-height: 1;" viewBox="0 0 24 24" width="40" xmlns="http://www.w3.org/2000/svg"><title>Grok</title><path d="M9.27 15.29l7.978-5.897c.391-.29.95-.177 1.137.272.98 2.369.542 5.215-1.41 7.169-1.951 1.954-4.667 2.382-7.149 1.406l-2.711 1.257c3.889 2.661 8.611 2.003 11.562-.953 2.341-2.344 3.066-5.539 2.388-8.42l.006.007c-.983-4.232.242-5.924 2.75-9.383.06-.082.12-.164.179-.248l-3.301 3.305v-.01L9.267 15.292M7.623 16.723c-2.792-2.67-2.31-6.801.071-9.184 1.761-1.763 4.647-2.483 7.166-1.425l2.705-1.25a7.808 7.808 0 00-1.829-1A8.975 8.975 0 005.984 5.83c-2.533 2.536-3.33 6.436-1.962 9.764 1.022 2.487-.653 4.246-2.34 6.022-.599.63-1.199 1.259-1.682 1.925l7.62-6.815"></path></svg>`,
  qwen: '<svg height="40" style="flex: 0 0 auto; line-height: 1;" viewBox="0 0 24 24" width="40" xmlns="http://www.w3.org/2000/svg"><title>Qwen</title><path d="M12.604 1.34c.393.69.784 1.382 1.174 2.075a.18.18 0 00.157.091h5.552c.174 0 .322.11.446.327l1.454 2.57c.19.337.24.478.024.837-.26.43-.513.864-.76 1.3l-.367.658c-.106.196-.223.28-.04.512l2.652 4.637c.172.301.111.494-.043.77-.437.785-.882 1.564-1.335 2.34-.159.272-.352.375-.68.37-.777-.016-1.552-.01-2.327.016a.099.099 0 00-.081.05 575.097 575.097 0 01-2.705 4.74c-.169.293-.38.363-.725.364-.997.003-2.002.004-3.017.002a.537.537 0 01-.465-.271l-1.335-2.323a.09.09 0 00-.083-.049H4.982c-.285.03-.553-.001-.805-.092l-1.603-2.77a.543.543 0 01-.002-.54l1.207-2.12a.198.198 0 000-.197 550.951 550.951 0 01-1.875-3.272l-.79-1.395c-.16-.31-.173-.496.095-.965.465-.813.927-1.625 1.387-2.436.132-.234.304-.334.584-.335a338.3 338.3 0 012.589-.001.124.124 0 00.107-.063l2.806-4.895a.488.488 0 01.422-.246c.524-.001 1.053 0 1.583-.006L11.704 1c.341-.003.724.032.9.34zm-3.432.403a.06.06 0 00-.052.03L6.254 6.788a.157.157 0 01-.135.078H3.253c-.056 0-.07.025-.041.074l5.81 10.156c.025.042.013.062-.034.063l-2.795.015a.218.218 0 00-.2.116l-1.32 2.31c-.044.078-.021.118.068.118l5.716.008c.046 0 .08.02.104.061l1.403 2.454c.046.081.092.082.139 0l5.006-8.76.783-1.382a.055.055 0 01.096 0l1.424 2.53a.122.122 0 00.107.062l2.763-.02a.04.04 0 00.035-.02.041.041 0 000-.04l-2.9-5.086a.108.108 0 010-.113l.293-.507 1.12-1.977c.024-.041.012-.062-.035-.062H9.2c-.059 0-.073-.026-.043-.077l1.434-2.505a.107.107 0 000-.114L9.225 1.774a.06.06 0 00-.053-.031zm6.29 8.02c.046 0 .058.02.034.06l-.832 1.465-2.613 4.585a.056.056 0 01-.05.029.058.058 0 01-.05-.029L8.498 9.841c-.02-.034-.01-.052.028-.054l.216-.012 6.722-.012z" fill="url(#lobe-icons-qwen-_r_j_)" fill-rule="nonzero"></path><defs><linearGradient id="lobe-icons-qwen-_r_j_" x1="0%" x2="100%" y1="0%" y2="0%"><stop offset="0%" stop-color="#6336E7" stop-opacity=".84"></stop><stop offset="100%" stop-color="#6F69F7" stop-opacity=".84"></stop></linearGradient></defs></svg>',
  zhipu: `<svg fill="white" fill-rule="evenodd" height="1em" style="flex:none;line-height:1" viewBox="0 0 24 24" width="1em" xmlns="http://www.w3.org/2000/svg"><title>Z.ai</title><path d="M12.105 2L9.927 4.953H.653L2.83 2h9.276zM23.254 19.048L21.078 22h-9.242l2.174-2.952h9.244zM24 2L9.264 22H0L14.736 2H24z"/></svg>`,
  custom: `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>`,
} as const

const providers: Provider[] = [
  {
    id: 'openai',
    name: 'OpenAI',
    icon: ICONS.openai,
    baseUrl: '',
    needsBase: false,
    models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'o1', 'o3-mini'],
  },
  {
    id: 'anthropic',
    name: 'Anthropic',
    icon: ICONS.anthropic,
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
    icon: ICONS.google,
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
    icon: ICONS.deepseek,
    baseUrl: 'https://api.deepseek.com/v1',
    needsBase: false,
    models: ['openai/deepseek-chat', 'openai/deepseek-reasoner'],
  },
  {
    id: 'kimi',
    name: 'Kimi',
    icon: ICONS.kimi,
    baseUrl: '',
    needsBase: false,
    models: [
      'moonshot/kimi-k2-turbo-preview',
      'moonshot/kimi-latest',
      'moonshot/moonshot-v1-128k',
      'moonshot/moonshot-v1-32k',
      'moonshot/moonshot-v1-8k',
    ],
  },
  {
    id: 'grok',
    name: 'Grok',
    icon: ICONS.grok,
    baseUrl: '',
    needsBase: false,
    models: [
      'xai/grok-3',
      'xai/grok-3-mini',
      'xai/grok-2',
      'xai/grok-2-vision-1212',
    ],
  },
  {
    id: 'qwen',
    name: 'Qwen',
    icon: ICONS.qwen,
    baseUrl: '',
    needsBase: false,
    models: [
      'dashscope/qwen-max',
      'dashscope/qwen-plus',
      'dashscope/qwen-turbo',
      'dashscope/qwen-long',
      'dashscope/qwen3-235b-a22b',
    ],
  },
  {
    id: 'zhipu',
    name: 'GLM',
    icon: ICONS.zhipu,
    baseUrl: '',
    needsBase: false,
    models: [
      'zhipu/glm-4-plus',
      'zhipu/glm-4-air',
      'zhipu/glm-4-flash',
      'zhipu/glm-4-long',
    ],
  },
  {
    id: 'mistral',
    name: 'Mistral',
    icon: ICONS.mistral,
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
    icon: ICONS.custom,
    baseUrl: '',
    needsBase: true,
    models: [],
  },
]

const customBaseUrl = ref('')
const customModel = ref('')
const customSubModel = ref('')
const selectedProvider = ref<string>('custom')
const form = ref({ apiKey: '', baseUrl: '', model: '', systemPrompt: '', subModel: '' })
const modelOptions = ref<{ label: string; value: string }[]>([])
const subModelOptions = ref<{ label: string; value: string }[]>([])
const fetchingModels = ref(false)
const testing = ref(false)

/** 保证当前填的 value 在可选项里(否则 n-select 会显示空) */
function ensureOption(options: { label: string; value: string }[], value: string) {
  if (!value) return options
  if (options.some(o => o.value === value)) return options
  return [{ label: value, value }, ...options]
}

const currentProviderNeedsBase = computed(() => {
  const p = providers.find(p => p.id === selectedProvider.value)
  return p?.needsBase ?? false
})
const systemPromptPresets = computed(() => [
  { label: t('modelSetting.presetCode'), text: t('modelSetting.presetCodeText') },
  { label: t('modelSetting.presetTranslate'), text: t('modelSetting.presetTranslateText') },
  { label: t('modelSetting.presetWriting'), text: t('modelSetting.presetWritingText') },
  { label: t('modelSetting.presetData'), text: t('modelSetting.presetDataText') },
  { label: t('modelSetting.presetCreative'), text: t('modelSetting.presetCreativeText') },
])
 
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
    subModel: settings.value.subModel || '',
  }

  const model = settings.value.model || ''
  const baseUrl = settings.value.baseUrl || ''
  customBaseUrl.value = settings.value.baseUrl || ''
  customModel.value = settings.value.model || ''
  customSubModel.value = settings.value.subModel || ''
  // 如果有 baseUrl 说明是自定义
  if (baseUrl) {
    selectedProvider.value = 'custom'
    modelOptions.value = model ? [{ label: model, value: model }] : []
    subModelOptions.value = form.value.subModel ? [{ label: form.value.subModel, value: form.value.subModel }] : []
    return
  }

  // 没有 baseUrl 则按模型前缀匹配厂商
  const matched = providers.find(p =>
    p.id !== 'custom' && p.models.some(m => m === model)
  )
  if (matched) {
    selectedProvider.value = matched.id
    modelOptions.value = matched.models.map(m => ({ label: m, value: m }))
    subModelOptions.value = ensureOption([...modelOptions.value], form.value.subModel)
  } else {
    selectedProvider.value = 'custom'
    modelOptions.value = model ? [{ label: model, value: model }] : []
    subModelOptions.value = form.value.subModel ? [{ label: form.value.subModel, value: form.value.subModel }] : []
  }
})

function selectProvider(p: Provider) {
  // 离开自定义时，先保存当前填的内容
  if (selectedProvider.value === 'custom') {
    customBaseUrl.value = form.value.baseUrl
    customModel.value = form.value.model
    customSubModel.value = form.value.subModel
  }

  selectedProvider.value = p.id

  if (p.id === 'custom') {
    // 切回自定义时，恢复之前保存的内容
    form.value.baseUrl = customBaseUrl.value
    form.value.model = customModel.value
    form.value.subModel = customSubModel.value
    modelOptions.value = customModel.value
      ? [{ label: customModel.value, value: customModel.value }]
      : []
    subModelOptions.value = customSubModel.value
      ? [{ label: customSubModel.value, value: customSubModel.value }]
      : []
  } else {
    form.value.baseUrl = p.baseUrl
    modelOptions.value = p.models.map(m => ({ label: m, value: m }))
    form.value.model = p.models[0] || ''
    // 子 Agent 模型不强制跟随主模型;但换了厂商后原来的值可能失效,失效则清空(回退用主模型)
    form.value.subModel = p.models.includes(form.value.subModel) ? form.value.subModel : ''
    subModelOptions.value = ensureOption([...modelOptions.value], form.value.subModel)
  }
}

async function handleFetchModels() {
  if (!form.value.apiKey || !form.value.baseUrl) {
    message.warning(t('modelSetting.needApiKeyAndBase'))
    return
  }
  fetchingModels.value = true
  try {
    const models = await fetchModels(form.value.apiKey, form.value.baseUrl)
    // 自定义接口的模型统一加 openai/ 前缀
    const options = models.map(id => ({ label: id, value: id }))
    modelOptions.value = options
    // 拉到的模型列表同样给子 Agent 选择器用(保留已填但不在列表里的值)
    subModelOptions.value = ensureOption([...options], form.value.subModel)
    if (models.length > 0) {
      message.success(t('modelSetting.fetchSuccess', { count: models.length }))
      if (!form.value.model) {
        form.value.model = models[0]
        customModel.value = models[0]
      }
    } else {
      message.warning(t('modelSetting.fetchEmpty'))
    }
  } catch (e: any) {
    message.error(t('modelSetting.fetchFail', { msg: e.message }))
  } finally {
    fetchingModels.value = false
  }
}

async function handleTest() {
  if (!form.value.apiKey) {
    message.warning(t('modelSetting.needApiKey'))
    return
  }
  testing.value = true
  try {
    await testConnection(form.value.apiKey, form.value.baseUrl)
    message.success(t('modelSetting.connectionSuccess'))
  } catch (e: any) {
    message.error(t('modelSetting.connectionFail', { msg: e.message }))
  } finally {
    testing.value = false
  }
}

const BACKEND_URL = 'http://127.0.0.1:8000'

async function handleSave() {
  saveSettings(form.value)
  // 同步 default provider 到后端 providers.json，让 generate_title / maybe_compress / pet-forge 等
  // 走非流式 chat() 的后台路径能拿到当前 model+key+base（否则会拿 providers.json 里旧 default dead value）。
  // 失败不影响前端已保存，仅提示警告。
  try {
    const resp = await fetch(`${BACKEND_URL}/providers`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: 'default',
        model: form.value.model,
        api_key: form.value.apiKey,
        api_base: form.value.baseUrl,
        sub_model: form.value.subModel || '',
      }),
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    await fetch(`${BACKEND_URL}/providers/default/activate`, { method: 'POST' })
  } catch (e: any) {
    message.warning(t('modelSetting.syncBackendFail', { msg: e.message }))
  }
  message.success(t('modelSetting.saved'))
  setTimeout(() => router.back(), 300)
}

function handleReset() {
  resetSettings()
  form.value = { apiKey: '', baseUrl: '', model: '', systemPrompt: '', subModel: '' }
  modelOptions.value = []
  subModelOptions.value = []
  selectedProvider.value = 'custom'
  message.info(t('modelSetting.resetDone'))
}
</script>

<style scoped>
.setting-page {
  height: 100vh;
  background: var(--bg-app);
  display: flex;
  flex-direction: column;
  color: var(--text-primary);
}

.setting-card-wrapper {
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 16px;
  overflow: hidden;
}

.setting-card {
  width: 100%;
  max-width: 520px;
  max-height: calc(100vh - 80px);
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  border-radius: var(--radius-lg, 12px);
  background: var(--bg-surface);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-md, 0 4px 12px rgba(0, 0, 0, 0.18));
}

.setting-card :deep(.n-card-header) {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}

.setting-card :deep(.n-card-header__main) {
  color: var(--text-primary);
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
  background: var(--accent-soft);
  border-radius: 2px;
}

.scrollable-form::-webkit-scrollbar-thumb:hover {
  background: var(--accent-soft-hover);
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
  gap: 6px;
  padding: 10px 6px;
  border-radius: var(--radius-md, 8px);
  border: 1px solid var(--border);
  cursor: pointer;
  transition: all var(--duration-base, 180ms) var(--ease-standard, ease);
  background: var(--surface-hover);
}

.provider-card:hover {
  border-color: var(--accent-border);
  background: var(--accent-soft);
}

.provider-card.active {
  border-color: var(--accent-500, #EF6B6E);
  background: var(--accent-soft);
}

.provider-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  color: var(--text-secondary);
  transition: color var(--duration-base, 180ms) var(--ease-standard, ease);
}

.provider-icon :deep(svg) {
  display: block;
  width: 22px;
  height: 22px;
}

.provider-card:hover .provider-icon,
.provider-card.active .provider-icon {
  color: var(--accent-300, #F7A85B);
}

.provider-name {
  font-size: 11px;
  color: var(--text-secondary);
  text-align: center;
}

.provider-card.active .provider-name {
  color: var(--text-primary);
}

.preset-tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0;
  margin-top: 2px;
}

/* 预设标签前的说明文字 */
.preset-label {
  font-size: 11px;
  color: var(--text-secondary);
  margin-right: 6px;
  margin-bottom: 4px;
}

/* 输入框 + 说明/标签的竖向排列容器(n-form-item 的 blank 是 flex 行，需抱成列) */
.field-stack {
  display: flex;
  flex-direction: column;
  width: 100%;
}

/* 表单项下方的说明文案 */
.field-hint {
  font-size: 11px;
  line-height: 1.5;
  color: var(--text-tertiary, var(--text-secondary));
  margin-top: 4px;
}

.scrollable-form :deep(.n-form-item-feedback-wrapper) {
  display: none !important;
}
.scrollable-form :deep(.n-form-item .n-form-item-feedback) {
  display: none !important;
}

/* 表单项分组:三块之间用留白隔开 */
.form-section {
  margin-bottom: 22px;
}
.form-section:last-of-type {
  margin-bottom: 0;
}

/* 同一块内相邻的 n-form-item 之间留一点间距,避免紧贴 */
.form-section > :deep(.n-form-item + .n-form-item) {
  margin-top: 10px;
}

/* label 与输入框间距:直接覆盖 label padding(顶部留白略小、底部间隙稍大) */
.form-section :deep(.n-form-item-label) {
  padding: 4px 0 9px 2px;
}
</style>
