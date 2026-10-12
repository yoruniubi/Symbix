/** 桌宠 spritesheet 的切片契约(与 pet-forge 的 pack_spritesheet 常量保持一致)。 */
export const SHEET_FRAME_W = 192
export const SHEET_FRAME_H = 208
export const SHEET_COLS = 8
export const SHEET_MIN_ROWS = 9

/**
 * 纹理是否满足 Home.vue 的切片契约。
 *
 * 宽度必须精确(每行 8 帧);高度至少 9 行且是帧高的整数倍
 * (旧 Codex 皮肤有 11 行的,多出来的行会被忽略,不算错)。
 * 尺寸不符的图「能加载成功但切片错位」,必须当成不可用,否则宠物会变成一坨错位马赛克。
 */
export function fitsSheetContract(width: number, height: number): boolean {
  return (
    width === SHEET_FRAME_W * SHEET_COLS &&
    height >= SHEET_FRAME_H * SHEET_MIN_ROWS &&
    height % SHEET_FRAME_H === 0
  )
}
