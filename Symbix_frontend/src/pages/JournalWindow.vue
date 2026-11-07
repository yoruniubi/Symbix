<template>
  <div class="journal-window">
    <TitleBar />

    <div class="journal-content">
      <!-- 顶部：手账 / 记忆库 两个视角 -->
      <div class="journal-tabs">
        <button
          type="button"
          class="tab-btn"
          :class="{ active: tab === 'daily' }"
          @click="switchTab('daily')"
        >{{ t('journal.tabDaily') }}</button>
        <button
          type="button"
          class="tab-btn"
          :class="{ active: tab === 'library' }"
          @click="switchTab('library')"
        >
          {{ t('journal.tabLibrary') }}
          <span v-if="libSummary.total" class="tab-badge">{{ libSummary.total }}</span>
        </button>
      </div>

      <template v-if="tab === 'daily'">
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
      </template>

      <!-- ═══ 记忆库：全库搜索 + 分类汇总 ═══ -->
      <template v-else>
        <!-- 搜索框 -->
        <div class="lib-search">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <circle cx="11" cy="11" r="7" />
            <line x1="16.5" y1="16.5" x2="21" y2="21" />
          </svg>
          <input
            v-model="libQuery"
            class="lib-search-input"
            type="text"
            :placeholder="t('journal.searchPlaceholder')"
            @input="onSearchInput"
          />
          <button v-if="libQuery" type="button" class="lib-search-clear" @click="clearSearch">×</button>
        </div>

        <!-- 分类汇总：点一下只看这一类，再点取消 -->
        <div class="lib-summary">
          <button
            v-for="card in libGroupCards"
            :key="card.key || 'all'"
            type="button"
            class="lib-group-card"
            :class="[card.key || 'all', { active: libGroup === card.key, empty: !card.count }]"
            @click="toggleGroup(card.key)"
          >
            <span class="lib-group-count">{{ card.count }}</span>
            <span class="lib-group-label">{{ card.label }}</span>
          </button>
        </div>

        <!-- 结果计数 / 重置 -->
        <div class="lib-meta">
          <span>{{ t('journal.libCount', { num: libQuery ? libMatched : libSummary.total }) }}</span>
          <span v-if="libQuery && libLiteral" class="lib-meta-hint">{{ t('journal.libExact', { num: libLiteral }) }}</span>
          <button
            v-if="libQuery || libGroup"
            type="button"
            class="lib-reset"
            @click="resetFilters"
          >{{ t('journal.resetFilter') }}</button>
        </div>

        <div v-if="libLoading" class="journal-loading">
          <div class="spinner"></div>
          <span>{{ t('journal.libLoading') }}</span>
        </div>

        <div v-else-if="libError" class="journal-empty">
          <div class="empty-icon">😔</div>
          <div class="empty-title">{{ libError }}</div>
          <button type="button" class="retry-btn" @click="loadLibrary">{{ t('journal.retry') }}</button>
        </div>

        <div v-else-if="!libItems.length" class="journal-empty">
          <div class="empty-icon">🔍</div>
          <div class="empty-title">{{ t('journal.searchEmpty') }}</div>
        </div>

        <div v-else class="lib-list">
          <div v-for="it in libItems" :key="it.id" class="lib-item">
            <span class="lib-cat" :class="`g-${it.group}`">{{ catLabel(it) }}</span>
            <div class="lib-body">
              <div class="lib-text" v-html="highlight(it.content)"></div>
              <div class="lib-sub">
                <span v-if="it.match" class="lib-match" :class="it.match">
                  {{ it.match === 'literal' ? t('journal.matchLiteral') : t('journal.matchSemantic') }}
                </span>
                <span v-if="fmtDate(it.created_at)" class="lib-date">{{ fmtDate(it.created_at) }}</span>
              </div>
            </div>
          </div>
        </div>

        <div v-if="libItems.length && libMatched > libItems.length" class="lib-truncated">
          {{ t('journal.libTruncated', { shown: libItems.length, total: libMatched }) }}
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import TitleBar from '@/components/TitleBar.vue'
const { t, te } = useI18n()
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
  // 顺手把记忆库的汇总拉回来：tab 上的总数徽标要立刻有数字，
  // 用户点进记忆库时也不用再等一次请求
  void loadLibrary()
})

// ═══════════════════════════════════════════════════════════════
// 记忆库：全库搜索 + 分类汇总
//
// 手账是「按天翻」，记忆库是「按需要找」—— 用户想找一条记得过的事时，
// 既不想逐天翻，也不确定当初是哪天记的。
// ═══════════════════════════════════════════════════════════════

type JournalTab = 'daily' | 'library'

interface LibItem {
  id: number
  content: string
  category: string
  category_label: string
  group: string
  group_label: string
  created_at: string
  score: number
  match: '' | 'literal' | 'semantic'
}

interface LibGroup {
  key: string
  label: string
  count: number
  categories: Array<{ key: string; label: string; count: number }>
}

interface LibSummary {
  groups: LibGroup[]
  total: number
}

const tab = ref<JournalTab>('daily')
const libQuery = ref('')
const libGroup = ref('')
const libLoading = ref(false)
const libError = ref('')
const libItems = ref<LibItem[]>([])
const libMatched = ref(0)
const libLiteral = ref(0)
const libSummary = ref<LibSummary>({ groups: [], total: 0 })

/** 「全部」卡片 + 四个分组卡片，点哪张就只留哪一类 */
const libGroupCards = computed(() => [
  { key: '', label: t('journal.groupAll'), count: libSummary.value.total },
  ...libSummary.value.groups.map((g) => ({ key: g.key, label: groupLabel(g.key, g.label), count: g.count })),
])

/** 后端给 key + 中文兜底，优先用 i18n 里的译文 */
function groupLabel(key: string, fallback: string): string {
  const path = `journal.group.${key}`
  return te(path) ? t(path) : fallback
}

function catLabel(item: LibItem): string {
  const path = `journal.cat.${item.category}`
  return te(path) ? t(path) : item.category_label
}

/** created_at 是 UTC ISO 串，列表里只看日期就够 */
function fmtDate(iso: string): string {
  return iso ? String(iso).slice(0, 10) : ''
}

function escapeHtml(text: string): string {
  const map: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }
  return text.replace(/[&<>"']/g, (c) => map[c] ?? c)
}

/** 命中词高亮：先转义再包 <mark>，只包关键词字面出现的位置 */
function highlight(text: string): string {
  const safe = escapeHtml(text)
  const query = libQuery.value.trim()
  if (!query) return safe
  const tokens = query
    .split(/\s+/)
    .filter((tk) => tk.length > 0)
    .sort((a, b) => b.length - a.length)
  let out = safe
  for (const token of tokens) {
    const pattern = escapeHtml(token).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    if (!pattern) continue
    out = out.replace(new RegExp(pattern, 'gi'), (m) => `<mark>${m}</mark>`)
  }
  return out
}

async function loadLibrary(): Promise<void> {
  libLoading.value = true
  libError.value = ''
  try {
    const params = new URLSearchParams({ limit: '200' })
    if (libQuery.value.trim()) params.set('q', libQuery.value.trim())
    if (libGroup.value) params.set('group', libGroup.value)
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), 10000)
    const res = await fetch(`${BACKEND_URL}/journal/memories?${params.toString()}`, {
      signal: ctrl.signal,
    })
    clearTimeout(timer)
    if (!res.ok) {
      const body = await res.text()
      throw new Error(body || `HTTP ${res.status}`)
    }
    const data = await res.json()
    libItems.value = Array.isArray(data.items) ? data.items : []
    libMatched.value = Number(data.matched) || 0
    libLiteral.value = Number(data.literal_matched) || 0
    libSummary.value = data.summary && Array.isArray(data.summary.groups)
      ? data.summary
      : { groups: [], total: 0 }
  } catch (e: any) {
    libError.value = e?.name === 'AbortError' ? t('journal.timeout') : (e?.message || String(e))
    libItems.value = []
    libMatched.value = 0
    libLiteral.value = 0
  } finally {
    libLoading.value = false
  }
}

/** 边打字边搜会打后端,300ms 静默再发 */
let searchTimer: ReturnType<typeof setTimeout> | null = null
function onSearchInput(): void {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    void loadLibrary()
  }, 300)
}

function switchTab(next: JournalTab): void {
  tab.value = next
  // 记忆库首次进入才拉数据,来回切 tab 不重复请求
  if (next === 'library' && !libItems.value.length && !libSummary.value.total) {
    void loadLibrary()
  }
}

function toggleGroup(key: string): void {
  // 点「全部」或再点一次同一类 → 取消筛选
  libGroup.value = libGroup.value === key ? '' : key
  void loadLibrary()
}

function clearSearch(): void {
  libQuery.value = ''
  void loadLibrary()
}

function resetFilters(): void {
  libQuery.value = ''
  libGroup.value = ''
  void loadLibrary()
}
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
/* ═══ 顶部 tab：手账 / 记忆库 ═══ */
.journal-tabs {
  display: flex;
  gap: 6px;
  margin-bottom: 12px;
  padding: 3px;
  background: var(--surface-hover, rgba(38, 34, 32, 0.04));
  border-radius: var(--radius-md);
}

.tab-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 7px 10px;
  border: none;
  border-radius: var(--radius-sm, 6px);
  background: transparent;
  color: var(--text-secondary, #6f675f);
  font-size: 13px;
  cursor: pointer;
  transition: all var(--duration-fast, 120ms) ease;
}

.tab-btn:hover {
  color: var(--text-primary, #262220);
}

.tab-btn.active {
  background: var(--bg-surface, #fff);
  color: var(--text-primary, #262220);
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(38, 34, 32, 0.08);
}

.tab-badge {
  font-size: 10px;
  line-height: 1;
  padding: 2px 5px;
  border-radius: 8px;
  background: var(--accent-soft, rgba(239, 107, 110, 0.12));
  color: var(--accent-600, #e2515f);
  font-weight: 600;
}

/* ═══ 记忆库：搜索框 ═══ */
.lib-search {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  margin-bottom: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg-surface, #fff);
  color: var(--text-secondary, #6f675f);
}

.lib-search:focus-within {
  border-color: var(--accent-500, #ef6b6e);
}

.lib-search-input {
  flex: 1;
  min-width: 0;
  border: none;
  outline: none;
  background: transparent;
  font-size: 13px;
  color: var(--text-primary, #262220);
}

.lib-search-clear {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  border: none;
  border-radius: 50%;
  background: var(--surface-active, rgba(38, 34, 32, 0.08));
  color: var(--text-secondary, #6f675f);
  font-size: 13px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.lib-search-clear:hover {
  background: var(--accent-soft, rgba(239, 107, 110, 0.16));
  color: var(--accent-600, #e2515f);
}

/* ═══ 记忆库：分类汇总卡 ═══ */
.lib-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(78px, 1fr));
  gap: 8px;
  margin-bottom: 12px;
}

.lib-group-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 10px 6px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg-surface, #fff);
  cursor: pointer;
  transition: all var(--duration-fast, 120ms) ease;
}

.lib-group-card:hover {
  border-color: var(--accent-border, rgba(239, 107, 110, 0.4));
}

.lib-group-card.active {
  border-color: var(--accent-500, #ef6b6e);
  background: var(--accent-soft, rgba(239, 107, 110, 0.1));
}

.lib-group-card.empty {
  opacity: 0.55;
}

.lib-group-count {
  font-size: 19px;
  font-weight: 700;
  color: var(--text-primary, #262220);
  line-height: 1.2;
}

.lib-group-card.constraint .lib-group-count {
  color: #c2410c;
}

.lib-group-card.personal .lib-group-count {
  color: #2563eb;
}

.lib-group-card.project .lib-group-count {
  color: #047857;
}

.lib-group-card.other .lib-group-count {
  color: var(--text-secondary, #6f675f);
}

.lib-group-label {
  font-size: 11px;
  color: var(--text-secondary, #6f675f);
  white-space: nowrap;
}

/* ═══ 记忆库：结果计数 ═══ */
.lib-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--text-secondary, #6f675f);
}

.lib-meta-hint {
  padding: 1px 6px;
  border-radius: 6px;
  background: var(--surface-hover, rgba(38, 34, 32, 0.05));
}

.lib-reset {
  margin-left: auto;
  border: none;
  background: transparent;
  color: var(--accent-600, #e2515f);
  font-size: 12px;
  cursor: pointer;
  padding: 2px 4px;
}

.lib-reset:hover {
  text-decoration: underline;
}

/* ═══ 记忆库：结果列表 ═══ */
.lib-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.lib-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg-surface, #fff);
}

.lib-cat {
  flex-shrink: 0;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 6px;
  background: var(--surface-hover, rgba(38, 34, 32, 0.06));
  color: var(--text-secondary, #6f675f);
  white-space: nowrap;
}

.lib-cat.g-constraint {
  background: rgba(194, 65, 12, 0.1);
  color: #c2410c;
}

.lib-cat.g-personal {
  background: rgba(37, 99, 235, 0.1);
  color: #2563eb;
}

.lib-cat.g-project {
  background: rgba(4, 120, 87, 0.1);
  color: #047857;
}

.lib-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.lib-text {
  font-size: 13px;
  line-height: 1.55;
  color: var(--text-primary, #262220);
  word-break: break-word;
}

.lib-text :deep(mark) {
  background: var(--accent-soft, rgba(239, 107, 110, 0.22));
  color: var(--accent-600, #e2515f);
  border-radius: 3px;
  padding: 0 2px;
}

.lib-sub {
  display: flex;
  align-items: center;
  gap: 8px;
}

.lib-match {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 5px;
  background: var(--surface-hover, rgba(38, 34, 32, 0.06));
  color: var(--text-secondary, #6f675f);
}

.lib-match.literal {
  background: var(--accent-soft, rgba(239, 107, 110, 0.14));
  color: var(--accent-600, #e2515f);
}

.lib-date {
  font-size: 11px;
  color: var(--text-secondary, #9a938b);
}

.lib-truncated {
  margin-top: 10px;
  text-align: center;
  font-size: 11px;
  color: var(--text-secondary, #9a938b);
}
</style>