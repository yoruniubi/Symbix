/**
 * token 数中文量级换算(全应用统一,替代旧的 x.xk 格式)。
 * ≥1亿 → 亿;≥1万 → 万;≥1千 → 千;其余原样。
 * 千万档显示为「1200万」而不是「0.12亿」,符合日常表达习惯。
 */
export function fmtTokens(n: number | undefined | null): string {
  const v = Math.max(0, Math.round(n || 0))
  if (v >= 1e8) return `${trim(v / 1e8)}亿`
  if (v >= 1e4) return `${trim(v / 1e4)}万`
  if (v >= 1e3) return `${trim(v / 1e3)}千`
  return String(v)
}

/** 小数位收敛:整数不带小数点,一位小数够用,百位以上直接取整 */
function trim(x: number): string {
  if (x >= 100) return String(Math.round(x))
  return x.toFixed(1).replace(/\.0$/, '')
}
