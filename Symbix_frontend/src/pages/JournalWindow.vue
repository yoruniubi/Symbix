<template>
  <div class="journal-window">
    <TitleBar />

    <div class="journal-content">
      <!-- 顶部:日期导航 -->
      <div class="journal-header">
        <button
          type="button"
          class="nav-btn"
          :disabled="loading"
          @click="prevDay"
          :title="t('journal.prevDay')"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>
        <div class="date-display">
          <span class="date-main">{{ currentDate }}</span>
          <span class="date-label">{{ t('journal.title') }}</span>
        </div>
        <button
          type="button"
          class="nav-btn"
          :disabled="loading"
          @click="nextDay"
          :title="t('journal.nextDay')"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="9 18 15 12 9 6" />
          </svg>
        </button>
      </div>

      <!-- 加载态 -->
      <div v-if="loading" class="journal-loading">
        <div class="spinner"></div>
        <span>{{ t('journal.loading') }}</span>
      </div>

      <!-- 错误态 -->
      <div v-else-if="loadError" class="journal-empty">
        <div class="empty-icon">😔</div>
        <div class="empty-title">{{ loadError }}</div>
        <button type="button" class="retry-btn" @click="loadDay(currentDate)">
          {{ t('journal.retry') }}
        </button>
      </div>

      <!-- 内容 -->
      <div v-else class="journal-body">
        <!-- 今日统计(温馨计数器) -->
        <div class="stats-row">
          <div class="stat-card">
            <div class="stat-num">{{ stats.message_count }}</div>
            <div class="stat-label">{{ t('journal.msgCount') }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-num">{{ stats.memory_count }}</div>
            <div class="stat-label">{{ t('journal.memCount') }}</div>
          </div>
        </div>

        <!-- 今日记忆(AI 记住了什么) -->
        <section v-if="memories.length" class="journal-section">
          <div class="section-title">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M18 12a6 6 0 0 0-12 0" />
              <path d="M18 12v4a2 2 0 0 1-2 2h-4" />
              <circle cx="12" cy="12" r="10" />
            </svg>
            {{ t('journal.sectionMemories') }}
          </div>
          <div class="memory-list">
            <div v-for="m in memories" :key="m.id" class="memory-item">
              <span class="memory-cat">{{ m.category_label }}</span>
              <span class="memory-text">{{ m.content }}</span>
            </div>
          </div>
        </section>

        <!-- AI 的小巧思 -->
        <section v-if="aiTips.length" class="journal-section">
          <div class="section-title">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10" />
              <path d="M9.5 9.5a2.5 2.5 0 0 1 5 0c0 2-3 2.5-3 4" />
              <line x1="12" y1="18" x2="12.01" y2="18" />
            </svg>
            {{ t('journal.sectionTips') }}
          </div>
          <div class="tips-list">
            <div v-for="(tip, i) in aiTips" :key="i" class="tip-item">
              <span class="tip-thought">💭 {{ tip.thought }}</span>
              <span class="tip-content">{{ tip.content }}</span>
            </div>
          </div>
        </section>

        <!-- 空态 -->
        <div v-if="!memories.length && !aiTips.length && !loading" class="journal-empty">
          <div class="empty-icon">📖</div>
          <div class="empty-title">{{ t('journal.empty') }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import TitleBar from '@/components/TitleBar.vue'

const { t } = useI18n()

const BACKEND_URL = 'http://127.0.0.1:8000'

interface Tip {
  content: string
  thought: string
  category_label: string
}
interface JournalData {
  date: string
  memories: Array<{ id: number; content: string; category: string; category_label: string; status: string; created_at: string }>
  ai_tips: Tip[]
  stats: { message_count: number; memory_count: number }
}

// 日期用本地时间,YYYY-MM-DD
function todayStr(): string {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

const currentDate = ref(todayStr())
const loading = ref(false)
const loadError = ref('')
const journal = ref<JournalData | null>(null)

const memories = computed(() => journal.value?.memories ?? [])
const aiTips = computed(() => journal.value?.ai_tips ?? [])
const stats = computed(() => journal.value?.stats ?? { message_count: 0, memory_count: 0 })

async function loadDay(date: string) {
  loading.value = true
  loadError.value = ''
  try {
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), 10000)
    const res = await fetch(`${BACKEND_URL}/journal/daily?date=${date}`, {
      signal: ctrl.signal,
    })
    clearTimeout(timer)
    if (!res.ok) {
      const body = await res.text()
      throw new Error(body || `HTTP ${res.status}`)
    }
    journal.value = await res.json()
  } catch (e: any) {
    loadError.value = e?.name === 'AbortError' ? t('journal.timeout') : (e?.message || String(e))
    journal.value = null
  } finally {
    loading.value = false
  }
}

function shiftDay(dir: number) {
  const d = new Date(currentDate.value + 'T00:00:00')
  d.setDate(d.getDate() + dir)
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  currentDate.value = `${y}-${m}-${day}`
  void loadDay(currentDate.value)
}
function prevDay() { shiftDay(-1) }
function nextDay() { shiftDay(1) }

onMounted(() => {
  void loadDay(currentDate.value)
})
</script>

<style scoped>
.journal-window {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-app);
  color: var(--text-primary, #222);
}

.journal-content {
  margin-top: 32px; /* TitleBar 高度 */
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

/* ── 顶部导航 ── */
.journal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
}

.nav-btn {
  width: 34px;
  height: 34px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  color: var(--text-primary, #262220);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background var(--duration-fast, 120ms) ease;
}

.nav-btn:hover:not(:disabled) {
  background: var(--surface-hover, rgba(38, 34, 32, 0.04));
}

.nav-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.date-display {
  text-align: center;
}

.date-main {
  display: block;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary, #222);
}

.date-label {
  display: block;
  font-size: 11px;
  color: var(--text-secondary, #6f675f);
  margin-top: 2px;
}

/* ── 加载 / 空态 ── */
.journal-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 0;
  gap: 12px;
  color: var(--text-secondary, #888);
  font-size: 13px;
}

.spinner {
  width: 26px;
  height: 26px;
  border: 3px solid var(--surface-active, rgba(38, 34, 32, 0.07));
  border-top-color: var(--accent-500, #ef6b6e);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.journal-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 0;
  gap: 10px;
  color: var(--text-secondary, #888);
}

.empty-icon {
  font-size: 40px;
}

.empty-title {
  font-size: 13px;
  color: var(--text-secondary, #888);
}

.retry-btn {
  margin-top: 8px;
  padding: 6px 16px;
  border: none;
  border-radius: var(--radius-md);
  background: var(--accent-500, #ef6b6e);
  color: #fff;
  cursor: pointer;
  font-size: 13px;
}

/* ── 统计行 ── */
.stats-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-bottom: 16px;
}

.stat-card {
  background: var(--surface-hover, rgba(38, 34, 32, 0.04));
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 14px;
  text-align: center;
}

.stat-num {
  font-size: 22px;
  font-weight: 700;
  color: var(--accent-500, #ef6b6e);
}

.stat-label {
  font-size: 11px;
  color: var(--text-secondary, #888);
  margin-top: 2px;
}

/* ── 区块 ── */
.journal-section {
  margin-bottom: 18px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #222);
  margin-bottom: 10px;
}

.section-title svg {
  color: var(--accent-500, #ef6b6e);
}

/* 记忆列表 */
.memory-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.memory-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  background: var(--surface-hover, rgba(38, 34, 32, 0.04));
  border-radius: var(--radius-md);
  padding: 10px 12px;
}

.memory-cat {
  flex-shrink: 0;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 6px;
  background: var(--accent-soft, rgba(239, 107, 110, 0.1));
  color: var(--accent-600, #e2515f);
}

.memory-text {
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-primary, #222);
}

/* AI 小巧思 */
.tips-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tip-item {
  background: var(--accent-soft, rgba(239, 107, 110, 0.1));
  border-left: 3px solid var(--accent-500, #ef6b6e);
  border-radius: var(--radius-md);
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.tip-thought {
  font-size: 12px;
  font-weight: 600;
  color: var(--accent-500, #ef6b6e);
}

.tip-content {
  font-size: 13px;
  color: var(--text-primary, #222);
  line-height: 1.5;
}

/* 滚动条 */
.journal-content::-webkit-scrollbar {
  width: 8px;
}

.journal-content::-webkit-scrollbar-thumb {
  background: var(--scrollbar, rgba(38, 34, 32, 0.12));
  border-radius: 4px;
}
</style>