export const PET_FRAME_W = 192
export const PET_FRAME_H = 208
export const PET_SHEET_COLS = 8

export type PetState =
  | 'idle'
  | 'runningRight'
  | 'runningLeft'
  | 'waving'
  | 'jumping'
  | 'failed'
  | 'progress'
  | 'patrol'
  | 'coding'

export interface PetRow {
  row: number
  frames: number
}

export const PET_ROWS: Record<PetState, PetRow> = {
  idle: { row: 0, frames: 6 },
  runningRight: { row: 1, frames: 8 },
  runningLeft: { row: 2, frames: 8 },
  waving: { row: 3, frames: 4 },
  jumping: { row: 4, frames: 5 },
  failed: { row: 5, frames: 7 },
  progress: { row: 6, frames: 6 },
  patrol: { row: 7, frames: 6 },
  coding: { row: 8, frames: 6 },
}

/** 持续循环的状态；其余是播完回 idle 的一次性动作。 */
export const PET_LOOP_STATES: ReadonlySet<PetState> = new Set<PetState>([
  'idle',
  'patrol',
  'runningRight',
  'runningLeft',
])

/** progress 行的有效步数（0%…100%）；后面重复的 100% 填充帧不算步数。 */
export const PET_PROGRESS_STEPS = 6

/**
 * 个别动作的原图帧并非严格按时间顺序排列，允许在不改素材的情况下重排/重复帧。
 * failed：站立 → 蹲下 → 跪地 → 趴倒，最后重复趴倒作为落地停留。
 * 注：行 5 里确实还有第 8 帧，但它是收勢回站的过渡帧，直接播完会显得“倒了又站起来”，
 *     所以只用前 7 帧（idx ≤ 6）。
 */
export const PET_FRAME_SEQUENCES: Partial<Record<PetState, readonly number[]>> = {
  failed: [0, 1, 3, 5, 6, 6, 6],
}

/**
 * 已完成工具调用数 → progress 行帧下标（0…5）。
 * 第 1 次工具完成停在 20%，第 6 次及以后停在 100%，之后靠收尾状态切走。
 */
export function petProgressFrameIndex(completed: number): number {
  if (!Number.isFinite(completed) || completed <= 0) return 0
  return Math.min(PET_PROGRESS_STEPS - 1, Math.floor(completed))
}

/**
 * 后端 action / 历史状态名 → 行。
 *
 * 注意 `waiting`（后端 propose_plan 发的「计划待确认」）在契约里没有对应行，
 * 退回 idle：那一行的真身是进度条，拿来当待机循环会变成进度条来回刷。
 */
const PET_STATE_ALIASES: Record<string, PetState> = {
  idle: 'idle',
  stand: 'idle',
  waiting: 'idle',
  wait: 'idle',

  runningright: 'runningRight',
  right: 'runningRight',
  runright: 'runningRight',
  moveright: 'runningRight',

  runningleft: 'runningLeft',
  left: 'runningLeft',
  runleft: 'runningLeft',
  moveleft: 'runningLeft',

  waving: 'waving',
  wave: 'waving',
  greet: 'waving',
  greeting: 'waving',
  attention: 'waving',

  jumping: 'jumping',
  jump: 'jumping',
  happy: 'jumping',
  celebrate: 'jumping',
  play: 'jumping',
  done: 'jumping',
  complete: 'jumping',
  success: 'jumping',
  scheduledjob: 'jumping',
  taskdone: 'jumping',

  failed: 'failed',
  fail: 'failed',
  error: 'failed',
  sad: 'failed',
  concerned: 'failed',
  confused: 'failed',

  progress: 'progress',
  progressbar: 'progress',
  percent: 'progress',

  patrol: 'patrol',
  walk: 'patrol',
  frontmove: 'patrol',
  running: 'patrol',

  coding: 'coding',
  code: 'coding',
  thinking: 'coding',
  think: 'coding',
  review: 'coding',
  laptop: 'coding',
  keyboard: 'coding',
  working: 'coding',
  busy: 'coding',
}

/** 归一化键：小写 + 去掉 - 和 _。 */
export function normalizePetActionKey(raw: string): string {
  return String(raw || '').trim().replace(/[-_]/g, '').toLowerCase()
}

/** 解析后端 action / 旧状态名，无法识别返回 null。 */
export function resolvePetState(raw: string | null | undefined): PetState | null {
  if (!raw) return null
  const key = normalizePetActionKey(raw)
  if (!key) return null
  return PET_STATE_ALIASES[key] ?? null
}
