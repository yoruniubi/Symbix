import {
  PET_FRAME_SEQUENCES,
  PET_LOOP_STATES,
  PET_PROGRESS_STEPS,
  PET_ROWS,
  normalizePetActionKey,
  petProgressFrameIndex,
  resolvePetState,
} from '../src/utils/petRows.ts'

let failed = 0

function check(name: string, actual: unknown, expected: unknown) {
  const a = JSON.stringify(actual)
  const e = JSON.stringify(expected)
  if (a !== e) {
    console.error(`FAIL ${name}: got ${a}, want ${e}`)
    failed++
  } else {
    console.log(`ok   ${name}`)
  }
}

// ── Codex 官方行契约 ─────────────────────────────────────────
check('行 0 = idle', PET_ROWS.idle, { row: 0, frames: 6 })
check('行 1 = 朝右移动', PET_ROWS.runningRight, { row: 1, frames: 8 })
check('行 2 = 朝左移动', PET_ROWS.runningLeft, { row: 2, frames: 8 })
check('行 3 = 打招呼', PET_ROWS.waving, { row: 3, frames: 4 })
check('行 4 = 开心跳', PET_ROWS.jumping, { row: 4, frames: 5 })
check('行 5 = 报错(7 帧,跳帧表避开收势帧)', PET_ROWS.failed, { row: 5, frames: 7 })
check('failed 跳帧表', PET_FRAME_SEQUENCES.failed, [0, 1, 3, 5, 6, 6, 6])
check('跳帧表索引不越界', Math.max(...(PET_FRAME_SEQUENCES.failed as number[])), PET_ROWS.failed.frames - 1)
check('行 6 = 进度条', PET_ROWS.progress, { row: 6, frames: 6 })
check('行 7 = 巡逻', PET_ROWS.patrol, { row: 7, frames: 6 })
check('行 8 = 敲键盘', PET_ROWS.coding, { row: 8, frames: 6 })

// 行号必须是 0..8 且不重复，改行表时最容易犯的错
const rows = Object.values(PET_ROWS).map((r) => r.row).sort((a, b) => a - b)
check('行号连续且唯一', rows, [0, 1, 2, 3, 4, 5, 6, 7, 8])

// ── 循环状态 ─────────────────────────────────────────────────
check('循环态只有 idle/patrol/左右移动', [...PET_LOOP_STATES].sort(), [
  'idle',
  'patrol',
  'runningLeft',
  'runningRight',
])
check('进度条不循环', PET_LOOP_STATES.has('progress'), false)
check('敲键盘不循环(由 agentThinking 单独判定)', PET_LOOP_STATES.has('coding'), false)

// ── 进度条帧映射 ─────────────────────────────────────────────
check('0 个工具 → 0%', petProgressFrameIndex(0), 0)
check('1 个工具 → 20%', petProgressFrameIndex(1), 1)
check('3 个工具 → 60%', petProgressFrameIndex(3), 3)
check('6 个工具 → 100%', petProgressFrameIndex(6), PET_PROGRESS_STEPS - 1)
check('超出上限不越界', petProgressFrameIndex(99), PET_PROGRESS_STEPS - 1)
check('负数/NaN 兜底', [petProgressFrameIndex(-3), petProgressFrameIndex(NaN)], [0, 0])

// ── action 别名 ──────────────────────────────────────────────
check('后端 happy → 行 4', resolvePetState('happy'), 'jumping')
check('后端 thinking → 行 8', resolvePetState('thinking'), 'coding')
check('旧名 review → 行 8', resolvePetState('review'), 'coding')
check('旧名 running → 行 7', resolvePetState('running'), 'patrol')
check('大小写/连字符容错', resolvePetState('Running-Right'), 'runningRight')
check('下划线容错', resolvePetState('scheduled_job'), 'jumping')
// 关键回归：waiting 在契约里是进度条行，绝不能当待机循环播
check('waiting 退回 idle 而不是进度条', resolvePetState('waiting'), 'idle')
check('未知 action 返回 null', resolvePetState('definitely-not-a-state'), null)
check('空值返回 null', [resolvePetState(''), resolvePetState(null), resolvePetState(undefined)], [
  null,
  null,
  null,
])
check('归一化键', normalizePetActionKey('  Run_Right '), 'runright')

if (failed > 0) {
  console.error(`\n${failed} 项失败`)
  process.exit(1)
}
console.log('\nALL PASS')
