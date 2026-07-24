<template>
  <div class="skin-window">
    <TitleBar />

    <div class="skin-content">
      <!-- Header -->
      <div class="header-row">
        <div class="header-text">
          <h1 class="title">桌宠皮肤</h1>
          <p class="subtitle">管理与切换当前桌宠外观</p>
        </div>
        <div class="header-meta">
          <span class="count-badge">{{ availablePets.length }} 套</span>
        </div>
      </div>

      <!-- 添加方式：两种入口 -->
      <section class="add-section">
        <div class="section-label">添加皮肤</div>
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
              <div class="add-card-title">
                Skill 生成
                <span v-if="!skillReady" class="soon-tag">待接入</span>
              </div>
              <div class="add-card-desc">通过 Skill 生成新的桌宠皮肤素材</div>
            </div>
            <svg class="add-card-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </button>

          <!-- 方式 2：Codex 桌宠导入 -->
          <n-upload
            :custom-request="handleUpload"
            accept=".webp,.png,.jpg,.jpeg"
            :show-file-list="false"
            class="add-card-upload"
          >
            <button type="button" class="add-card">
              <div class="add-card-icon import">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="17 8 12 3 7 8" />
                  <line x1="12" y1="3" x2="12" y2="15" />
                </svg>
              </div>
              <div class="add-card-body">
                <div class="add-card-title">Codex 导入</div>
                <div class="add-card-desc">导入 Codex 桌宠图片（webp / png / jpg）</div>
              </div>
              <svg class="add-card-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="9 18 15 12 9 6" />
              </svg>
            </button>
          </n-upload>
        </div>
      </section>

      <!-- 皮肤列表 -->
      <section class="list-section">
        <div class="section-label">已有皮肤</div>
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
                title="删除皮肤"
                @click.stop="removePet(pet.id)"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
            <span class="skin-name">{{ pet.displayName }}</span>
            <span v-if="pet.source" class="skin-source">{{ pet.source }}</span>
          </div>
        </div>
        <n-empty v-else description="暂无皮肤" size="small" style="margin-top: 24px;" />
      </section>
    </div>

    <!-- Skill 生成弹窗（占位，等 skill 接入） -->
    <n-modal
      v-model:show="showSkillModal"
      preset="card"
      title="Skill 生成皮肤"
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
          Skill 生成流程待接入。<br />
          指定 Skill 名称后，将在此填写生成参数。
        </p>
        <n-form label-placement="top" size="small" style="width: 100%;">
          <n-form-item label="皮肤名称">
            <n-input v-model:value="skillForm.name" placeholder="例如 my-pet" disabled />
          </n-form-item>
          <n-form-item label="描述 / 提示词">
            <n-input
              v-model:value="skillForm.prompt"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 4 }"
              placeholder="描述你想要的桌宠外观…"
              disabled
            />
          </n-form-item>
        </n-form>
      </div>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showSkillModal = false">关闭</n-button>
          <n-button type="primary" disabled>生成（待接入）</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useMessage } from 'naive-ui'
import TitleBar from '@/components/TitleBar.vue'
import { Assets, Texture } from 'pixi.js'

interface PetSkin {
  id: string
  displayName: string
  preview: string
  source?: string
}

const message = useMessage()

/** Skill 是否已接入（你指定 skill 后改为 true 并实现 generate） */
const skillReady = ref(false)

const currentPetId = ref('02')
const availablePets = ref<PetSkin[]>([
  { id: '02', displayName: 'Pet 02', preview: '/pet/02/spritesheet.webp', source: '内置' },
])

const showSkillModal = ref(false)
const skillForm = ref({
  name: '',
  prompt: '',
})

// ── Skill 生成（占位） ──────────────────────────────────────
function openSkillGenerate() {
  if (!skillReady.value) {
    showSkillModal.value = true
    return
  }
  // TODO: 接入 skill 后在此发起生成
  showSkillModal.value = true
}

// ── Codex / 本地图片导入 ────────────────────────────────────
async function parseSkin(file: File): Promise<PetSkin | null> {
  try {
    const previewUrl = URL.createObjectURL(file)

    const img = new Image()
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve()
      img.onerror = () => reject(new Error('无法读取图片'))
      img.src = previewUrl
    })

    const newId = `custom_${Date.now()}`
    const displayName = file.name.replace(/\.(webp|png|jpe?g)$/i, '') || '自定义皮肤'

    return {
      id: newId,
      displayName,
      preview: previewUrl,
      source: '导入',
    }
  } catch (e: any) {
    message.error(`解析文件失败：${e.message || e}`)
    return null
  }
}

async function handleUpload({ file }: { file: { file?: File | null } }) {
  const uploadedFile = file?.file
  if (!uploadedFile) {
    message.warning('未选择文件')
    return
  }

  const validTypes = ['image/webp', 'image/png', 'image/jpeg', 'image/jpg']
  if (!validTypes.includes(uploadedFile.type)) {
    message.warning('请上传 webp、png 或 jpg 格式的图片')
    return
  }

  const maxSize = 5 * 1024 * 1024
  if (uploadedFile.size > maxSize) {
    message.warning('文件大小不能超过 5MB')
    return
  }

  const loadingMsg = message.loading('正在导入皮肤…', { duration: 0 })

  try {
    const newPet = await parseSkin(uploadedFile)
    if (!newPet) {
      loadingMsg.destroy()
      return
    }

    availablePets.value.push(newPet)

    const savedPets: PetSkin[] = JSON.parse(localStorage.getItem('customPets') || '[]')
    savedPets.push(newPet)
    localStorage.setItem('customPets', JSON.stringify(savedPets))

    loadingMsg.destroy()
    message.success('皮肤导入成功！')
  } catch (e: any) {
    loadingMsg.destroy()
    message.error(`导入失败：${e.message || e}`)
  }
}

// ── 切换 / 删除 ─────────────────────────────────────────────
async function switchPet(pet: PetSkin) {
  try {
    currentPetId.value = pet.id
    await Assets.load<Texture>(pet.preview)
    message.success(`已切换到 ${pet.displayName}`)
    localStorage.setItem('currentPetId', pet.id)
    // TODO: 通知主窗口切换精灵
  } catch (e: any) {
    message.error(`加载失败：${e.message || e}`)
  }
}

function removePet(id: string) {
  availablePets.value = availablePets.value.filter(p => p.id !== id)
  const savedPets: PetSkin[] = JSON.parse(localStorage.getItem('customPets') || '[]')
  localStorage.setItem('customPets', JSON.stringify(savedPets.filter(p => p.id !== id)))
  if (currentPetId.value === id) {
    currentPetId.value = '02'
    localStorage.setItem('currentPetId', '02')
  }
  message.success('已删除皮肤')
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

.add-card-upload {
  width: 100%;
}

.add-card-upload :deep(.n-upload-trigger) {
  width: 100%;
  display: block;
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
