<template>
  <div class="skin-window">
    <TitleBar />
    <div class="skin-content">
      <h2 class="title">选择形象</h2>
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
  { id: '01', displayName: 'Pet 01', preview: '/pet/01/spritesheet.webp' },
  { id: '02', displayName: 'Pet 02', preview: '/pet/02/spritesheet.webp' },
])

async function switchPet(pet: { id: string; displayName: string; preview: string }) {
  try {
    currentPetId.value = pet.id
    // 预加载纹理以验证资源存在
    await Assets.load<Texture>(pet.preview)
    message.success(`已切换到 ${pet.displayName}`)
    // TODO: 通知主窗口切换精灵
  } catch (e: any) {
    message.error(`加载失败：${e.message}`)
  }
}

onMounted(() => {
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
  background: rgba(16, 16, 24, 0.95);
  color: white;
  padding-top: 32px;
  display: flex;
  flex-direction: column;
}

.skin-content {
  flex: 1;
  padding: 32px 24px;
  overflow-y: auto;
}

.title {
  font-size: 24px;
  font-weight: 600;
  color: #e0e0ff;
  margin: 0 0 24px 0;
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
  border-radius: 12px;
  border: 2px solid transparent;
  background: rgba(255, 255, 255, 0.03);
  cursor: pointer;
  transition: all 0.2s ease;
}

.skin-item:hover {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(99, 102, 241, 0.3);
}

.skin-item.active {
  border-color: #6366f1;
  background: rgba(99, 102, 241, 0.15);
}

.skin-item img {
  width: 96px;
  height: 96px;
  image-rendering: pixelated;
  object-fit: cover;
  object-position: 0 0;
  border-radius: 8px;
}

.skin-item span {
  font-size: 14px;
  color: #a0a0b8;
  font-weight: 500;
}

.skin-item.active span {
  color: #818cf8;
}

.skin-content::-webkit-scrollbar {
  width: 6px;
}

.skin-content::-webkit-scrollbar-thumb {
  background: #3a3a42;
  border-radius: 3px;
}
</style>