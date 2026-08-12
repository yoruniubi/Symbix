<template>
  <div class="skin-window">
    <TitleBar />

    <div class="skin-content">
      <!-- Header -->
      <div class="header-row">
        <div class="header-text">
          <h1 class="title">{{ t('skinWindow.title') }}</h1>
          <p class="subtitle">{{ t('skinWindow.subtitle') }}</p>
        </div>
        <div class="header-meta">
          <span class="count-badge">{{ t('skinWindow.count', { count: availablePets.length }) }}</span>
        </div>
      </div>

      <!-- 添加方式：两种入口 -->
      <section class="add-section">
        <div class="section-label">{{ t('skinWindow.addSection') }}</div>
        <div class="add-cards">
          <!-- 方式 1：Skill 生成 -->
          <button
            type="button"
            class="add-card"
            :class="{ disabled: !skillReady }"
            @click="openSkillGenerate"
          >
            <div class="add-card-icon skill">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5 12 2" />
                <line x1="12" y1="22" x2="12" y2="15.5" />
                <polyline points="22 8.5 12 15.5 2 8.5" />
              </svg>
            </div>
            <div class="add-card-body">
              <div class="add-card-title">{{ t('skinWindow.skillGenerate') }}<span v-if="!skillReady" class="soon-tag">{{ t('skinWindow.comingSoon') }}</span></div>
              <div class="add-card-desc">{{ t('skinWindow.skillGenerateDesc') }}</div>
            </div>
            <svg class="add-card-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </button>

          <!-- 方式 2：Codex 桌宠导入（Tauri 原生选目录 / 浏览器回退） -->
          <button type="button" class="add-card" @click="pickFolder">
            <div class="add-card-icon import">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
            </div>
            <div class="add-card-body">
              <div class="add-card-title">{{ t('skinWindow.codexImport') }}</div>
              <div class="add-card-desc">{{ t('skinWindow.codexImportDesc') }}</div>
            </div>
            <svg class="add-card-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </button>

        </div>
      </section>

      <!-- 皮肤列表 -->
      <section class="list-section">
        <div class="section-label">{{ t('skinWindow.existingSection') }}</div>
        <div v-if="availablePets.length > 0" class="skin-grid">
          <div
            v-for="pet in availablePets"
            :key="pet.id"
            class="skin-item"
            :class="{ active: currentPetId === pet.id }"
            @click="switchPet(pet)"
          >
            <div class="skin-preview-wrap">
              <img :src="pet.preview" :alt="pet.displayName" />
              <div v-if="currentPetId === pet.id" class="active-check">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              </div>
              <button
                v-if="pet.id.startsWith('custom_')"
                type="button"
                class="remove-btn"
                :title="t('skinWindow.removeBtn')"
                @click.stop="removePet(pet.id)"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
            <span class="skin-name">{{ pet.displayName }}</span>
            <span v-if="pet.source" class="skin-source">{{ t('skinWindow.' + pet.source) }}</span>
          </div>
        </div>
        <n-empty v-else :description="t('skinWindow.empty')" size="small" style="margin-top: 24px;" />
      </section>
    </div>

    <!-- Skill 生成弹窗 -->
    <n-modal
      v-model:show="showSkillModal"
      preset="card"
      :title="t('skinWindow.modalTitle')"
      style="width: 420px; max-width: 94vw;"
      :bordered="false"
      class="skill-modal"
    >
      <div class="skill-modal-body">
        <div class="skill-placeholder-icon">
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5 12 2" />
            <line x1="12" y1="22" x2="12" y2="15.5" />
            <polyline points="22 8.5 12 15.5 2 8.5" />
          </svg>
        </div>
        <p class="skill-placeholder-text">
          {{ t('skinWindow.skillGenerateDesc') }}<br />
          <span style="font-size: 11px; opacity: 0.7;">{{ t('skinWindow.modalHint') }}</span>
        </p>
        <n-form label-placement="top" size="small" style="width: 100%;">
          <n-form-item :label="t('skinWindow.modalName')">
            <n-input v-model:value="skillForm.name" :placeholder="t('skinWindow.namePlaceholder')" />
          </n-form-item>
          <n-form-item :label="t('skinWindow.modalPrompt')">
            <n-input
              v-model:value="skillForm.prompt"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 4 }"
              :placeholder="t('skinWindow.modalPromptPlaceholder')"
            />
          </n-form-item>
        </n-form>
      </div>
      <template #footer>
        <n-space justify="end">
          <n-button @click="closeSkillModal">{{ t('skinWindow.modalClose') }}</n-button>
          <n-button type="primary" @click="triggerSkillGenerate" :disabled="!canGenerateSkill">
            {{ t('skinWindow.modalGenerate') }}
          </n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useMessage } from 'naive-ui'
import { useRouter } from 'vue-router'
import TitleBar from '@/components/TitleBar.vue'
import { Assets, Texture } from 'pixi.js'
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
const skillList = ref([])
interface PetSkin {
  id: string
  displayName: string
  preview: string
  source?: string
}

/** 跨窗口通知主窗切换皮肤：localStorage + Tauri emit/emitTo 多通道 */
async function notifyPetSwitched(payload: {
  petId: string
  petFolder: string
  spritesheetPath: string
  displayName: string
}) {
  // 1) localStorage：同源多 webview 会触发 storage 事件（最稳兜底）
  try {
    localStorage.setItem('currentPetId', payload.petId)
    localStorage.setItem(
      'petSwitchSignal',
      JSON.stringify({ ...payload, ts: Date.now() }),
    )
  } catch (e) {
    console.warn('[skin] localStorage petSwitchSignal failed:', e)
  }

  // 2) Tauri 事件：全局 emit + 定向 main
  try {
    const { emit, emitTo } = await import('@tauri-apps/api/event')
    await emit('pet-switched', payload)
    try {
      await emitTo('main', 'pet-switched', payload)
    } catch (e) {
      console.warn('[skin] emitTo(main) failed:', e)
    }
  } catch (e) {
    console.warn('[skin] tauri emit pet-switched failed:', e)
  }
}


const message = useMessage()
const router = useRouter()

/** Skill 是否已接入（你指定 skill 后改为 true 并实现 generate） */
const skillReady = ref(true)

const currentPetId = ref('02')
const availablePets = ref<PetSkin[]>([
  { id: '02', displayName: 'Pet 02', preview: '/pet/02/spritesheet.webp', source: 'builtin' },
])

const showSkillModal = ref(false)
const skillForm = ref({
  name: '',
  prompt: '',
})

// ── Skill 生成 ──────────────────────────────────────────────
const BACKEND_URL = 'http://127.0.0.1:8000'

const canGenerateSkill = computed(() => {
  return !!skillForm.value.name.trim() && !!skillForm.value.prompt.trim()
})

async function openSkillGenerate() {
  showSkillModal.value = true
  // 尝试获取 skill 列表确认 pet-forge 可用
  try {
    const res = await fetch(`${BACKEND_URL}/skills`)
    const data = await res.json()
    skillList.value = data.skills
    const petForge = data.skills?.find((s: any) => s.name === 'pet-forge')
    if (!petForge) {
      message.warning(t('skinWindow.petForgeMissing'))
      skillReady.value = false
    } else {
      skillReady.value = true
    }
  } catch {
    // 后端不可用时仍可打开弹窗
  }
}

function closeSkillModal() {
  showSkillModal.value = false
}

async function triggerSkillGenerate() {
  if (!canGenerateSkill.value) return

  const petName = skillForm.value.name.trim()
  const prompt = skillForm.value.prompt.trim()
  if (!petName || !prompt) return

  // 构造发送给 AI 的消息
  const messageText = t('skinWindow.skillMessage', { name: petName, prompt })

  // 关闭弹窗
  closeSkillModal()

  // 通过 localStorage 传递消息给聊天窗口
  try {
    localStorage.setItem('pendingSkinGen', JSON.stringify({
      message: messageText,
      ts: Date.now(),
    }))
  } catch (e) {
    console.warn('[skin] 保存 pendingSkinGen 失败:', e)
  }

  // 跳转到聊天页面
  router.push('/chat')
}

// ── Codex 桌宠文件夹导入 ─────────────────────────────────────
/** 是否运行在 Tauri 桌面壳内 */
function isTauri(): boolean {
  return typeof window !== 'undefined' && !!(window as any).__TAURI_INTERNALS__
}

function pushImportedPet(pet: PetSkin) {
  availablePets.value.push(pet)
  const savedPets: PetSkin[] = JSON.parse(localStorage.getItem('customPets') || '[]')
  savedPets.push(pet)
  localStorage.setItem('customPets', JSON.stringify(savedPets))
}

/** 主路径：Tauri 原生选目录 → 只把路径发给后端本地拷贝（无浏览器上传确认、不卡） */
async function importViaTauriDialog() {
  const { open } = await import('@tauri-apps/plugin-dialog')
  const selected = await open({
    directory: true,
    multiple: false,
    title: '选择 Codex 桌宠文件夹（含 pet.json）',
  })
  if (!selected || typeof selected !== 'string') {
    // 用户取消
    return
  }

  const sourcePath = selected
  const folderName = sourcePath.replace(/[\\/]+$/, '').split(/[\\/]/).pop() || 'imported_pet'
  const loadingMsg = message.loading(t('skinWindow.uploadConfirm'), { duration: 0 })

  try {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 30_000)

    const res = await fetch(`${BACKEND_URL}/pet/import-path`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source_path: sourcePath, folder_name: folderName }),
      signal: controller.signal,
    })
    clearTimeout(timer)

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}))
      throw new Error((errData as any)?.detail || `HTTP ${res.status}`)
    }

    const result = await res.json()
    const displayName = result.display_name || folderName
    const preview = result.preview || `/pet/${folderName}/spritesheet.webp`

    pushImportedPet({
      id: `custom_${Date.now()}`,
      displayName,
      preview,
      source: 'imported',
    })

    loadingMsg.destroy()
    message.success(t('skinWindow.importSuccess', { name: displayName, count: result.files_saved ?? 0 }))
  } catch (e: any) {
    loadingMsg.destroy()
    if (e?.name === 'AbortError') {
      message.error(t('skinWindow.importTimeout'))
    } else {
      message.error(t('skinWindow.importFail', { msg: e.message || e }))
    }
  }
}

/**
 * 浏览器回退：用 webkitdirectory，但只上传白名单关键文件
 * （pet.json / spritesheet），避免整夹几百帧 multipart 卡死。
 * 仍会有浏览器「是否上传」确认——这是 Chromium 安全限制，无法去掉。
 */
async function importViaBrowserFallback() {
  const input = document.createElement('input')
  input.type = 'file'
  input.setAttribute('webkitdirectory', '')
  input.setAttribute('directory', '')
  input.multiple = true

  const files: FileList | null = await new Promise((resolve) => {
    input.onchange = () => resolve(input.files)
    input.oncancel = () => resolve(null)
    input.click()
  })

  if (!files || files.length === 0) return

  const folderName = files[0].webkitRelativePath?.split('/')[0] || 'imported_pet'
  const allowExact = new Set([
    'pet.json',
    'spritesheet.webp',
    'spritesheet.png',
    'spritesheet.json',
    'preview.webp',
    'preview.png',
  ])

  let hasPetJson = false
  const formData = new FormData()
  for (let i = 0; i < files.length; i++) {
    const f = files[i]
    const rel = (f.webkitRelativePath || f.name).replace(/\\/g, '/')
    const parts = rel.split('/')
    // 只取根目录一层文件
    if (parts.length !== 2) continue
    const base = parts[1]
    if (!allowExact.has(base) && !base.startsWith('spritesheet')) continue
    if (base === 'pet.json') hasPetJson = true
    formData.append('files', f, `${folderName}/${base}`)
  }
  formData.append('folder_name', folderName)

  if (!hasPetJson) {
    message.warning(t('skinWindow.importNoPetJson'))
    return
  }

  const loadingMsg = message.loading(t('skinWindow.uploading'), { duration: 0 })
  try {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 30_000)
    const res = await fetch(`${BACKEND_URL}/pet/import`, {
      method: 'POST',
      body: formData,
      signal: controller.signal,
    })
    clearTimeout(timer)

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}))
      throw new Error((errData as any)?.detail || `HTTP ${res.status}`)
    }
    const result = await res.json()
    const displayName = result.display_name || folderName

    pushImportedPet({
      id: `custom_${Date.now()}`,
      displayName,
      preview: `/pet/${folderName}/spritesheet.webp`,
      source: 'imported',
    })
    loadingMsg.destroy()
    message.success(t('skinWindow.importSimpleSuccess', { name: displayName }))
  } catch (e: any) {
    loadingMsg.destroy()
    if (e?.name === 'AbortError') {
      message.error(t('skinWindow.importTimeout'))
    } else {
      message.error(t('skinWindow.importFail', { msg: e.message || e }))
    }
  }
}

async function pickFolder() {
  if (isTauri()) {
    await importViaTauriDialog()
  } else {
    await importViaBrowserFallback()
  }
}


// ── 切换 / 删除 ─────────────────────────────────────────────
async function switchPet(pet: PetSkin) {
  try {
    // 预检纹理是否可加载（失败则不切、不提示成功）
    await Assets.load<Texture>(pet.preview)

    currentPetId.value = pet.id
    localStorage.setItem('currentPetId', pet.id)

    const folderName = pet.preview.replace(/^\/pet\//, '').replace(/\/.*$/, '')
    // 内置皮肤直接用 id；自定义皮肤从 preview 路径提取文件夹名
    const petFolder =
      pet.id === '02' || pet.id === '01' || !pet.id.startsWith('custom_')
        ? (pet.id.startsWith('custom_') ? folderName : pet.id)
        : folderName

    await notifyPetSwitched({
      petId: pet.id,
      petFolder,
      spritesheetPath: pet.preview,
      displayName: pet.displayName,
    })

    message.success(t('skinWindow.switchSuccess', { name: pet.displayName }))
  } catch (e: any) {
    message.error(t('skinWindow.loadFail', { msg: e.message || e }))
  }
}

function removePet(id: string) {
  availablePets.value = availablePets.value.filter(p => p.id !== id)
  const savedPets: PetSkin[] = JSON.parse(localStorage.getItem('customPets') || '[]')
  localStorage.setItem('customPets', JSON.stringify(savedPets.filter(p => p.id !== id)))
  if (currentPetId.value === id) {
    currentPetId.value = '02'
    void notifyPetSwitched({
      petId: '02',
      petFolder: '02',
      spritesheetPath: '/pet/02/spritesheet.webp',
      displayName: 'Pet 02',
    })
  }
  message.success(t('skinWindow.deleteSuccess'))
}


onMounted(() => {
  const savedPets: PetSkin[] = JSON.parse(localStorage.getItem('customPets') || '[]')
  if (savedPets.length > 0) {
    // 避免重复推入内置皮肤
    const existingIds = new Set(availablePets.value.map(p => p.id))
    for (const p of savedPets) {
      if (!existingIds.has(p.id)) availablePets.value.push(p)
    }
  }

  const savedPetId = localStorage.getItem('currentPetId')
  if (savedPetId) currentPetId.value = savedPetId
})
</script>

<style scoped>
.skin-window {
  width: 100vw;
  height: 100vh;
  background: var(--bg-app);
  color: var(--text-primary);
  padding-top: 32px;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  overflow: hidden;
}

.skin-content {
  flex: 1;
  min-height: 0;
  padding: 20px 24px 28px;
  overflow-y: auto;
  overscroll-behavior: contain;
}

/* ---- Header ---- */
.header-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 22px;
}

.header-text {
  min-width: 0;
}

.title {
  font-size: 22px;
  font-weight: 600;
  margin: 0 0 4px;
  background: var(--symbix-gradient, linear-gradient(135deg, #F7A85B 0%, #F2657A 55%, #E85C93 100%));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.subtitle {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
}

.count-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  color: var(--accent-300, #F7A85B);
  background: var(--accent-soft);
  border: 1px solid var(--accent-border, transparent);
  white-space: nowrap;
}

/* ---- Sections ---- */
.section-label {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  color: var(--text-muted, var(--text-secondary));
  margin-bottom: 10px;
}

.add-section {
  margin-bottom: 28px;
}

.list-section {
  margin-bottom: 8px;
}

/* ---- Add cards ---- */
.add-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

@media (max-width: 520px) {
  .add-cards {
    grid-template-columns: 1fr;
  }
}

.add-card {

  width: 100%;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 14px 14px 12px;
  border-radius: var(--radius-lg, 12px);
  border: 1px solid var(--border);
  background: var(--bg-surface, var(--surface-hover));
  color: inherit;
  cursor: pointer;
  text-align: left;
  transition: border-color var(--duration-base, 180ms) ease,
    background var(--duration-base, 180ms) ease,
    transform var(--duration-fast, 120ms) ease;
}

.add-card:hover:not(.disabled) {
  border-color: var(--accent-border, rgba(239, 107, 110, 0.45));
  background: var(--accent-soft);
  transform: translateY(-1px);
}

.add-card.disabled {
  opacity: 0.85;
  cursor: pointer; /* 仍可点开占位弹窗 */
}

.add-card-icon {
  width: 42px;
  height: 42px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.add-card-icon.skill {
  color: var(--accent-500, #EF6B6E);
  background: var(--accent-soft);
}

.add-card-icon.import {
  color: var(--info, #5B8AC4);
  background: rgba(91, 138, 196, 0.12);
}

.add-card-body {
  flex: 1;
  min-width: 0;
}

.add-card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 6px;
}

.add-card-desc {
  margin-top: 3px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.4;
}

.add-card-arrow {
  flex-shrink: 0;
  color: var(--text-muted, var(--text-secondary));
  opacity: 0.7;
}

.soon-tag {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 999px;
  color: var(--text-secondary);
  background: var(--surface-hover);
  border: 1px solid var(--border);
}

/* ---- Skin grid ---- */
.skin-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(128px, 1fr));
  gap: 14px;
}

.skin-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 14px 12px 12px;
  border-radius: var(--radius-lg, 12px);
  border: 2px solid transparent;
  background: var(--surface-hover);
  cursor: pointer;
  transition: all var(--duration-base, 180ms) var(--ease-standard, ease);
}

.skin-item:hover {
  background: var(--bg-elevated, var(--surface-active));
  border-color: var(--accent-border, rgba(239, 107, 110, 0.35));
}

.skin-item.active {
  border-color: var(--accent-500, #EF6B6E);
  background: var(--accent-soft);
}

.skin-preview-wrap {
  position: relative;
  width: 96px;
  height: 96px;
}

.skin-item img {
  width: 96px;
  height: 96px;
  image-rendering: pixelated;
  object-fit: cover;
  object-position: 0 0;
  border-radius: var(--radius-md, 8px);
  background: var(--bg-elevated, #2B2523);
  display: block;
}

.active-check {
  position: absolute;
  right: -4px;
  bottom: -4px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--accent-500, #EF6B6E);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.25);
}

.remove-btn {
  position: absolute;
  top: -6px;
  right: -6px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 1px solid var(--border);
  background: var(--bg-elevated, #2B2523);
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  opacity: 0;
  transition: opacity 120ms ease, color 120ms ease, background 120ms ease;
}

.skin-item:hover .remove-btn {
  opacity: 1;
}

.remove-btn:hover {
  color: var(--error, #D3555A);
  background: rgba(211, 85, 90, 0.12);
}

.skin-name {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 500;
  text-align: center;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.skin-item.active .skin-name {
  color: var(--accent-300, #F7A85B);
}

.skin-source {
  font-size: 11px;
  color: var(--text-muted, var(--text-secondary));
  opacity: 0.85;
}

/* ---- Skill modal ---- */
.skill-modal-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.skill-placeholder-icon {
  width: 64px;
  height: 64px;
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--accent-500, #EF6B6E);
  background: var(--accent-soft);
}

.skill-placeholder-text {
  margin: 0 0 4px;
  text-align: center;
  font-size: 13px;
  line-height: 1.55;
  color: var(--text-secondary);
}

/* ---- Scrollbar ---- */
.skin-content::-webkit-scrollbar {
  width: 5px;
}
.skin-content::-webkit-scrollbar-track {
  background: transparent;
}
.skin-content::-webkit-scrollbar-thumb {
  background: var(--scrollbar, var(--border));
  border-radius: 3px;
}
</style>