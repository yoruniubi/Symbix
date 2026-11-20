import { BACKEND_URL } from '@/utils/backend'

export function useApiClient() {
  function normalizeBaseUrl(url: string): string {
    let u = url.trim().replace(/\/+$/, '')
    if (!/^https?:\/\//i.test(u)) {
      u = 'https://' + u
    }
    const v1Match = u.match(/^(.*?\/v\d+)/i)
    if (v1Match) return v1Match[1]
    return u + '/v1'
  }

  /**
   * 取上游模型列表。
   *
   * **必须走后端**:浏览器直连上游会被 CORS 拦(上游中转网关普遍不返回
   * Access-Control-Allow-Origin),而后端发同样的请求不受浏览器策略约束。
   */
  async function fetchModels(apiKey: string, baseUrl: string): Promise<string[]> {
    const res = await fetch(`${BACKEND_URL}/providers/models`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: apiKey, api_base: baseUrl }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(`${res.status} ${err?.detail || res.statusText}`)
    }
    const data = await res.json()
    return (data.models || []).filter(Boolean)
  }

  async function testConnection(apiKey: string, baseUrl: string): Promise<void> {
    await fetchModels(apiKey, baseUrl)
  }

  async function chatCompletion(
    apiKey: string,
    baseUrl: string,
    model: string,
    messages: { role: string; content: string }[]
  ): Promise<string> {
    const base = normalizeBaseUrl(baseUrl)
    const endpoint = `${base}/chat/completions`
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`,
      },
      body: JSON.stringify({ model, messages }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error((err as any)?.error?.message || `HTTP ${res.status}`)
    }
    const data = await res.json()
    return data.choices?.[0]?.message?.content || '（无回复）'
  }

  return { normalizeBaseUrl, fetchModels, testConnection, chatCompletion }
}
