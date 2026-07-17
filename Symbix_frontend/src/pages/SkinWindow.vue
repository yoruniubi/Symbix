<template>
  <div class="skin-window">
    <TitleBar />
    <div class="skin-content">
      <div class="header-row">
        <h2 class="title">选择形象</h2>
        <n-upload
          :custom-request="handleUpload"
          accept=".webp,.png,.jpg,.jpeg"
          :show-file-list="false"
        >
          <n-button type="primary" size="small">
            <template #icon>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="17 8 12 3 7 8"></polyline>
                <line x1="12" y1="3" x2="12" y2="15"></line>
              </svg>
            </template>
            导入新皮肤
          </n-button>
        </n-upload>
      </div>
      <div class="skin-grid">
        <div
          v-for="pet in availablePets"
          :key="pet.id"
          class="skin-item"
          :class="{ active: currentPetId === pet.id }"
          @click="switchPet(pet)"
        >
          <img :src="pet.preview" :alt="pet.displayName" />
          <span>{{ pet.displayName }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useMessage } from 'naive-ui'
import TitleBar from '@/components/TitleBar.vue'
import { Assets, Texture, TextureSource } from 'pixi.js'

const message = useMessage()

const currentPetId = ref('02')
const availablePets = ref([
  { id: '02', displayName: 'Pet 02', preview: '/pet/02/spritesheet.webp' },
])

// 解析上传的皮肤文件
async function parseskin(file: File): Promise<{ id: string; displayName: string; preview: string } | null> {
  try {
    // 创建临时 URL 用于预览
    const previewUrl = URL.createObjectURL(file)
    
    // 验证是否为有效图片
    const img = new Image()
    await new Promise((resolve, reject) => {
      img.onload = resolve
      img.onerror = reject
      img.src = previewUrl
    })
    
    // 生成新的 ID（基于时间戳）
    const newId = `custom_${Date.now()}`
    const displayName = file.name.replace(/\.(webp|png|jpe?g)$/i, '')
    
    return {
      id: newId,
      displayName: displayName,
      preview: previewUrl,
    }
  } catch (e: any) {
    message.error(`解析文件失败：${e.message}`)
    return null
  }
}

// 处理文件上传
async function handleUpload({ file }: { file: { file: File } }) {
  const uploadedFile = file.file
  
  // 验证文件类型
  const validTypes = ['image/webp', 'image/png', 'image/jpeg', 'image/jpg']
  if (!validTypes.includes(uploadedFile.type)) {
    message.warning('请上传 webp、png 或 jpg 格式的图片')
    return
  }
  
  // 验证文件大小（最大 5MB）
  const maxSize = 5 * 1024 * 1024
  if (uploadedFile.size > maxSize) {
    message.warning('文件大小不能超过 5MB')
    return
  }
  
  const loadingMsg = message.loading('正在导入皮肤...', { duration: 0 })
  
  try {
    const newPet = await parseskin(uploadedFile)
    if (newPet) {
      // 添加到可用皮肤列表
      availablePets.value.push(newPet)
      
      // 保存到本地存储
      const savedPets = JSON.parse(localStorage.getItem('customPets') || '[]')
      savedPets.push(newPet)
      localStorage.setItem('customPets', JSON.stringify(savedPets))
      
      loadingMsg.destroy()
      message.success('皮肤导入成功！')
    } else {
      loadingMsg.destroy()
    }
  } catch (e: any) {
    loadingMsg.destroy()
    message.error(`导入失败：${e.message}`)
  }
}

async function switchPet(pet: { id: string; displayName: string; preview: string }) {
  try {
    currentPetId.value = pet.id
    // 预加载纹理以验证资源存在
    await Assets.load<Texture>(pet.preview)
    message.success(`已切换到 ${pet.displayName}`)
    
    // 保存当前选择
    localStorage.setItem('currentPetId', pet.id)
    // TODO: 通知主窗口切换精灵
  } catch (e: any) {
    message.error(`加载失败：${e.message}`)
  }
}

onMounted(() => {
  // 从本地存储加载自定义皮肤
  const savedPets = JSON.parse(localStorage.getItem('customPets') || '[]')
  if (savedPets.length > 0) {
    availablePets.value.push(...savedPets)
  }
  
  // 从本地存储加载当前选择的宠物
  const savedPetId = localStorage.getItem('currentPetId')
  if (savedPetId) {
    currentPetId.value = savedPetId
  }
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
}

.skin-content {
  flex: 1;
  padding: 32px 24px;
  overflow-y: auto;
}

.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}

.title {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.skin-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 16px;
}

.skin-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 16px;
  border-radius: var(--radius-lg, 12px);
  border: 2px solid transparent;
  background: var(--surface-hover);
  cursor: pointer;
  transition: all var(--duration-base, 180ms) var(--ease-standard, ease);
}

.skin-item:hover {
  background: var(--surface-active);
  border-color: var(--accent-border);
}

.skin-item.active {
  border-color: var(--accent-500, #EF6B6E);
  background: var(--accent-soft);
}

.skin-item img {
  width: 96px;
  height: 96px;
  image-rendering: pixelated;
  object-fit: cover;
  object-position: 0 0;
  border-radius: var(--radius-md, 8px);
}

.skin-item span {
  font-size: 14px;
  color: var(--text-secondary);
  font-weight: 500;
}

.skin-item.active span {
  color: var(--accent-300, #F7A85B);
}

.skin-content::-webkit-scrollbar {
  width: 6px;
}

.skin-content::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 3px;
}
</style>