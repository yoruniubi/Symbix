import { WebviewWindow } from '@tauri-apps/api/webviewWindow'

/** 更新提示窗口的 label，全局唯一，重复调用只把已有窗口提到前台 */
const UPDATE_LABEL = 'update'

/**
 * 打开「有新版本」的独立窗口。
 *
 * 为什么单独开窗口而不是在页面里弹 modal：桌宠主窗只有 280×260 且透明，
 * 聊天窗又可能被侧栏挤得很窄，把更新说明塞进去很难看。独立窗口可以有自己
 * 的尺寸/位置，关掉就是关掉，不影响任何页面。
 */
export async function openUpdateWindow(): Promise<void> {
  try {
    const existing = await WebviewWindow.getByLabel(UPDATE_LABEL)
    if (existing) {
      await existing.show()
      await existing.setFocus()
      return
    }
  } catch {
    // 窗口不存在时 getByLabel 可能抛错，继续走新建逻辑
  }

  try {
    new WebviewWindow(UPDATE_LABEL, {
      url: '/update',
      title: 'Symbix Update',
      width: 720,
      height: 640,
      minWidth: 520,
      minHeight: 420,
      resizable: true,
      decorations: false,
      transparent: true,
      center: true,
    })
  } catch (e) {
    console.error('Failed to open update window:', e)
  }
}
