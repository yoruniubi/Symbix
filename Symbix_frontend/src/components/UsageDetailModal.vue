<template>
  <n-modal
    :show="show"
    preset="card"
    :title="$t('usageModal.title')"
    style="width: 640px; max-width: 94vw;"
    :bordered="false"
    class="usage-modal"
    @update:show="emit('update:show', $event)"
  >
    <!-- 汇总三卡:今日 / 本周 / 本月 -->
    <div class="stat-row">
      <div v-for="card in cards" :key="card.key" class="stat-card">
        <div class="stat-label">{{ $t(`usageModal.${card.key}`) }}</div>
        <div class="stat-total">{{ fmtTokens(card.data.total) }}</div>
        <div class="stat-sub">
          ↑{{ fmtTokens(card.data.prompt) }} ↓{{ fmtTokens(card.data.output) }} · {{ card.data.calls }}
        </div>
      </div>
    </div>

    <!-- 最近 30 天逐日柱状:时间轴在下方 -->
    <div class="days-title">{{ $t('usageModal.recent') }}</div>
    <div v-if="!loaded" class="empty">{{ $t('usageModal.loading') }}</div>
    <div v-else-if="maxDayTotal === 0" class="empty">{{ $t('usageModal.empty') }}</div>
    <template v-else>
      <div class="chart" @mouseleave="hoverIdx = -1">
        <div
          v-for="(d, i) in days"
          :key="d.date"
          class="bar-slot"
          @mouseenter="hoverIdx = i"
        >
          <div class="bar-track">
            <div
              class="bar"
              :style="{ height: `${barHeight(d)}%` }"
            />
          </div>
        </div>
        <!-- 图表级共享气泡:固定悬浮在图表顶部,内容跟随 hover 的柱子,
             高度稳定不随模型数暴涨,也不会顶出图表区 -->
        <div v-if="hoverDay" class="chart-tip" :style="{ left: tipLeft }">
          <span class="tip-line strong">{{ $t('usageModal.dayTip', { date: hoverDay.date.slice(5), up: fmtTokens(hoverDay.prompt), down: fmtTokens(hoverDay.output), calls: hoverDay.calls }) }}</span>
          <span v-for="m in hoverDay.models" :key="m.name" class="tip-line">
            {{ m.name === '__other__' ? $t('usageModal.other') : shortModel(m.name) }} · {{ fmtTokens(m.total) }} ×{{ m.calls }}
          </span>
        </div>
      </div>
      <!-- 时间轴:稀疏标注,首/末必标,中间每 5 天一个 -->
      <div class="axis">
        <span
          v-for="(d, i) in days"
          :key="d.date"
          class="axis-tick"
        >
          <span v-if="showTick(i)" class="axis-label">{{ d.date.slice(5) }}</span>
        </span>
      </div>
      <div class="axis-hint">{{ $t('usageModal.range', { start: days[0]?.date?.slice(5), end: days[days.length - 1]?.date?.slice(5) }) }}</div>
    </template>
    <div class="foot-hint">{{ $t('usageModal.hint') }}</div>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NModal } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { fmtTokens } from '../utils/tokenFmt'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ (e: 'update:show', v: boolean): void }>()
const { t } = useI18n()

const BACKEND_URL = (import.meta as any).env?.VITE_BACKEND_URL || 'http://localhost:8000'

interface DayStat { date: string; prompt: number; output: number; total: number; calls: number; models?: DayModel[] }
interface DayModel { name: string; total: number; calls: number }
interface PeriodStat { prompt: number; output: number; tools: number; total: number; calls: number }
interface Summary { today: PeriodStat; week: PeriodStat; month: PeriodStat; days: DayStat[] }

const loaded = ref(false)
const summary = ref<Summary | null>(null)
const hoverIdx = ref(-1)

const cards = computed(() => [
  { key: 'today', data: summary.value?.today ?? zero() },
  { key: 'week', data: summary.value?.week ?? zero() },
  { key: 'month', data: summary.value?.month ?? zero() },
])
const days = computed(() => (summary.value?.days ?? []).filter(d => d.total > 0))
const maxDayTotal = computed(() => Math.max(0, ...days.value.map(d => d.total)))
const hoverDay = computed(() => days.value[hoverIdx.value] ?? null)
/** 气泡水平位置:对准 hover 柱的中心;贴边时往内收,避免溢出弹窗 */
const tipLeft = computed(() => {
  const n = days.value.length
  if (!n || hoverIdx.value < 0) return '50%'
  const pct = ((hoverIdx.value + 0.5) / n) * 100
  return `${Math.min(88, Math.max(12, pct))}%`
})

function zero(): PeriodStat {
  return { prompt: 0, output: 0, tools: 0, total: 0, calls: 0 }
}

/** 模型名缩短:openai/gpt-4o-mini → gpt-4o-mini,超长截尾 */
function shortModel(name: string): string {
  const tail = name.split('/').pop() || name
  return tail.length > 18 ? `${tail.slice(0, 17)}…` : tail
}

function barHeight(d: DayStat): number {
  if (!d.total || !maxDayTotal.value) return 0
  // 保底 4%:零星小用量也给一根可见小柱,否则完全看不见
  return Math.max(4, (d.total / maxDayTotal.value) * 100)
}

/** 时间轴稀疏标注:柱数少(≤15)时每根都标,多了才隔 5 天抽稀 */
function showTick(i: number): boolean {
  const n = days.value.length
  if (n <= 15) return true
  return i === 0 || i === n - 1 || i % 5 === 0
}

async function load(): Promise<void> {
  loaded.value = false
  try {
    const res = await fetch(`${BACKEND_URL}/usage/summary?days=30`)
    summary.value = await res.json()
  } catch {
    summary.value = null
  } finally {
    loaded.value = true
  }
}

// 每次打开都重新拉,保证数字最新
watch(() => props.show, (v) => { if (v) load() })
</script>

<style scoped>
.stat-row {
    display: flex;
    gap: 10px;
}
.stat-card {
    flex: 1;
    padding: 12px;
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    background: var(--bg-surface);
    text-align: center;
}
.stat-label {
    font-size: 12px;
    color: var(--text-secondary);
}
.stat-total {
    margin: 4px 0 2px;
    font-size: 22px;
    font-weight: 600;
    color: var(--text-primary);
    font-variant-numeric: tabular-nums;
}
.stat-sub {
    font-size: 11px;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
}
.days-title {
    margin: 16px 0 8px;
    font-size: 12px;
    font-weight: 600;
    color: var(--text-secondary);
}
.chart {
    display: flex;
    align-items: flex-end;
    gap: 3px;
    height: 190px;
    padding: 18px 2px 0;
}
.bar-slot {
    flex: 1;
    height: 100%;
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    position: relative;
}
.bar-track {
    height: 100%;
    display: flex;
    align-items: flex-end;
    justify-content: center;
}
.bar {
    width: 86%;
    max-width: 34px;
    min-height: 3px;
    border-radius: 3px 3px 0 0;
    background: var(--symbix-gradient-soft);
    transition: height var(--duration-base) var(--ease-standard);
}
.bar-slot:hover .bar {
    background: var(--accent-600);
}
/* 图表级共享气泡:固定悬浮在图表顶部,内容跟随 hover 的柱子 */
.chart {
    position: relative;
}
.chart-tip {
    position: absolute;
    top: 0;
    transform: translateX(-50%);
    padding: 5px 9px;
    border-radius: var(--radius-sm);
    background: var(--gray-800);
    color: #fff;
    font-size: 10px;
    line-height: 1.6;
    white-space: nowrap;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    pointer-events: none;
    z-index: 2;
    box-shadow: var(--shadow-md);
}
.tip-line {
    white-space: nowrap;
    color: rgba(255, 255, 255, 0.82);
}
.tip-line.strong {
    color: #fff;
    font-weight: 600;
    margin-bottom: 2px;
}
.axis {
    display: flex;
    gap: 3px;
    margin-top: 6px;
    border-top: 1px solid var(--border);
    padding-top: 4px;
}
.axis-tick {
    flex: 1;
    text-align: center;
}
.axis-label {
    font-size: 10px;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
}
.axis-hint {
    margin-top: 4px;
    text-align: right;
    font-size: 10px;
    color: var(--text-muted);
}
.empty {
    padding: 20px 0;
    text-align: center;
    font-size: 12px;
    color: var(--text-muted);
}
.foot-hint {
    margin-top: 12px;
    font-size: 11px;
    color: var(--text-muted);
}
</style>
