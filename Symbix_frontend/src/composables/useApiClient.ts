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

  async function fetchModels(apiKey: string, baseUrl: string): Promise<string[]> {
    const base = normalizeBaseUrl(baseUrl)
    const res = await fetch(`${base}/models`, {
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
      },
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(`${res.status} ${(err as any)?.error?.message || res.statusText}`)
    }
    const data = await res.json()
    return (data.data || data.models || [])
      .map((m: any) => m.id || m.name || String(m))
      .filter(Boolean)
      .sort()
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
