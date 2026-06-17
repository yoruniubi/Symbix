<template>
  <div class="pet-container" ref="containerRef">
    <canvas ref="canvasRef" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { Application, Texture, AnimatedSprite, Rectangle,TextureSource,Assets } from 'pixi.js'


const containerRef = ref<HTMLDivElement>()
const canvasRef = ref<HTMLCanvasElement>()

// 动画行定义（标准 Petdex 8x9 格式）
const ROWS = {
  idle:          { row: 0, frames: 6 },
  runningRight:  { row: 1, frames: 8 },
  runningLeft:   { row: 2, frames: 8 },
  waving:        { row: 3, frames: 4 },
  jumping:       { row: 4, frames: 5 },
  failed:        { row: 5, frames: 8 },
  waiting:       { row: 6, frames: 6 },
  running:       { row: 7, frames: 6 },
  review:        { row: 8, frames: 6 },
}

const FRAME_W = 192
const FRAME_H = 208
const COLS = 8
// const FPS = 8

let app: Application | null = null
let sprite: AnimatedSprite | null = null
let currentState = 'idle'
let baseSource: TextureSource | null = null
// 从 spritesheet 切割指定行的帧
function getFrames(source: TextureSource, row: number, frameCount: number) {
  return Array.from({ length: frameCount }, (_, i) => {
    return new Texture({
      source,  // 传 TextureSource，不是 Texture
      frame: new Rectangle(i * FRAME_W, row * FRAME_H, FRAME_W, FRAME_H),
    })
  })
}

function playState(state: keyof typeof ROWS, returnToIdle = true) {
  if (!sprite || !baseSource) return
  currentState = state
  const def = ROWS[state]
  sprite.textures = getFrames(baseSource as TextureSource, def.row, def.frames)
  sprite.loop = state === 'idle' || state === 'waiting'  // 只有这两个循环
  sprite.gotoAndPlay(0)

  // 非循环动画播完自动回 idle
  if (returnToIdle && !sprite.loop) {
    sprite.onComplete = () => playState('idle', false)
  } else {
    sprite.onComplete = undefined
  }
}

// 每隔随机时间插入一个待机动作
function scheduleRandomAction() {
  const delay = 5000 + Math.random() * 10000  // 5-15秒随机
  setTimeout(() => {
    if (currentState === 'idle') {
      const actions = ['waving', 'jumping'] as const
      const pick = actions[Math.floor(Math.random() * actions.length)]
      playState(pick)
    }
    scheduleRandomAction()  // 递归调度下一次
  }, delay)
}

onMounted(async () => {
  
  scheduleRandomAction()
  if (!canvasRef.value) return

  app = new Application()
  await app.init({
    canvas: canvasRef.value,
    width: FRAME_W * 2,
    height: FRAME_H * 2,
    backgroundAlpha: 0,
    resolution: window.devicePixelRatio || 1,
    autoDensity: true,
  })

  // 加载 spritesheet（把文件放到 public 目录下）
  const texture = await Assets.load('/pet/02/spritesheet.webp')
  baseSource = texture.source
  console.log('Loaded texture:', texture)
  console.log('Base texture source:', baseSource)
  const idleDef = ROWS.idle
  const frames = getFrames(texture.source, idleDef.row, idleDef.frames)

  sprite = new AnimatedSprite(frames)
  sprite.animationSpeed = 0.05
  sprite.scale.set(2)  // 放大 2 倍，原始 192x208 有点小
  sprite.loop = true
  sprite.play()

  app.stage.addChild(sprite)

  // 鼠标靠近切换 waving
  canvasRef.value.addEventListener('mouseenter', () => playState('waving'))
  canvasRef.value.addEventListener('mouseleave', () => playState('idle'))
  canvasRef.value.addEventListener('click', () => playState('jumping'))
})

onUnmounted(() => {
  app?.destroy(false)
})
</script>

<style scoped>
.pet-container {
  width: 100vw;
  height: 100vh;
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
}

canvas {
  image-rendering: pixelated;  /* 像素风格保持清晰 */
}
</style>