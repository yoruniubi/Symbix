/**
 * 日志脱敏工具 - 防止 API Key 等敏感信息在 console.log 中完整暴露
 */

/** 对 API Key 等敏感字符串脱敏：保留前4位 + *** + 后2位 */
export function maskSecret(value: string | undefined): string {
  if (!value) return ''
  if (value.length <= 6) return '***'
  return value.slice(0, 4) + '***' + value.slice(-2)
}

/** 深度克隆对象并对敏感字段脱敏 */
export function maskSensitive<T extends Record<string, any>>(obj: T, sensitiveKeys: string[] = ['api_key', 'apiKey', 'api_secret', 'secret', 'password', 'token']): Record<string, any> {
  const result: Record<string, any> = {}
  for (const [key, value] of Object.entries(obj)) {
    if (sensitiveKeys.some(k => key.toLowerCase().includes(k.toLowerCase()))) {
      result[key] = maskSecret(value)
    } else if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
      result[key] = maskSensitive(value, sensitiveKeys)
    } else {
      result[key] = value
    }
  }
  return result
}

/** 安全日志输出：自动脱敏 */
export function safeLog(label: string, data: any, sensitiveKeys?: string[]) {
  if (typeof data === 'object' && data !== null) {
    console.log(label, maskSensitive(data, sensitiveKeys))
  } else if (typeof data === 'string' && data.startsWith('sk-')) {
    console.log(label, maskSecret(data))
  } else {
    console.log(label, data)
  }
}