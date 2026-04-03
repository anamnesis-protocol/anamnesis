/**
 * API client for the Sovereign AI Context backend.
 * BASE_URL should point to the running FastAPI server.
 * In dev: set to your machine's LAN IP so Expo Go on device can reach it.
 *   e.g. "http://192.168.1.10:8000"
 * In production: your deployed API URL.
 */

let _baseUrl = 'http://localhost:8000'

export function setBaseUrl(url: string) {
  _baseUrl = url.replace(/\/$/, '')
}

export function getBaseUrl() {
  return _baseUrl
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${_baseUrl}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ChallengeResponse {
  token_id: string
  challenge_hex: string
}

export interface ProvisionStartResponse {
  token_id: string
  challenge_hex: string
  expires_at: string
}

export interface ProvisionCompleteResponse {
  token_id: string
  sections_pushed: string[]
  index_file_id: string
  vault_registered: boolean
  message: string
}

export interface VaultStatusResponse {
  token_id: string
  registered: boolean
  index_file_id: string | null
  message: string
}

export interface SessionOpenResponse {
  session_id: string
  token_id: string
  vault_sections: Record<string, string>
  sections_loaded: string[]
  created_at: string
  expires_at: string
}

export interface SessionCloseResponse {
  session_id: string
  sections_pushed: string[]
  hcs_sequence_number?: number
  message: string
}

export interface ModelInfo {
  id: string
  display: string
  provider: string
  available: boolean
}

export interface SkillSummary {
  id: string
  name: string
  description: string
  tags: string[]
  version: string
  created_at: string
}

export interface SkillDetail extends SkillSummary {
  updated_at: string
  input_schema: Record<string, unknown>
  instructions: string
  examples: Array<Record<string, unknown>>
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

export const api = {
  session: {
    challenge: (token_id: string) =>
      request<ChallengeResponse>('POST', '/session/challenge', { token_id }),

    open: (token_id: string, wallet_signature_hex: string, serial = 1) =>
      request<SessionOpenResponse>('POST', '/session/open', {
        token_id,
        wallet_signature_hex,
        serial,
      }),

    close: (session_id: string, updated_sections: Record<string, string> = {}) =>
      request<SessionCloseResponse>('POST', '/session/close', {
        session_id,
        updated_sections,
      }),
  },

  user: {
    status: (token_id: string) =>
      request<VaultStatusResponse>('GET', `/user/${encodeURIComponent(token_id)}/status`),

    provisionStart: (account_id: string, companion_name: string) =>
      request<ProvisionStartResponse>('POST', '/user/provision/start', {
        account_id,
        companion_name,
      }),

    provisionComplete: (token_id: string, wallet_signature_hex: string) =>
      request<ProvisionCompleteResponse>('POST', '/user/provision/complete', {
        token_id,
        wallet_signature_hex,
      }),
  },

  chat: {
    models: (session_id?: string) => {
      const qs = session_id ? `?session_id=${session_id}` : ''
      return request<{ models: ModelInfo[] }>('GET', `/chat/models${qs}`)
    },

    /** Returns the raw Response for SSE streaming. */
    streamMessage: (
      session_id: string,
      message: string,
      model: string,
      history: Array<{ role: string; content: string }> = []
    ): Promise<Response> =>
      fetch(`${_baseUrl}/chat/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id, message, model, history }),
      }),

    /** Demo server-side sign. */
    demoSign: (token_id: string) =>
      request<{ wallet_signature_hex: string }>('POST', '/demo/sign', { token_id }),
  },

  skills: {
    list: (session_id: string, tags?: string, name_contains?: string) => {
      const params = new URLSearchParams({ session_id })
      if (tags) params.set('tags', tags)
      if (name_contains) params.set('name_contains', name_contains)
      return request<{ token_id: string; skills: SkillSummary[] }>('GET', `/skills?${params}`)
    },

    get: (skill_id: string, session_id: string) =>
      request<SkillDetail>('GET', `/skills/${skill_id}?session_id=${session_id}`),

    upsert: (
      session_id: string,
      data: Partial<SkillDetail> & { name: string; description: string; instructions: string }
    ) =>
      request<{ skill_id: string; name: string; version: string; message: string }>(
        'POST',
        `/skills?session_id=${session_id}`,
        data
      ),

    delete: (skill_id: string, session_id: string) =>
      request<{ skill_id: string; deleted: boolean; message: string }>(
        'DELETE',
        `/skills/${skill_id}?session_id=${session_id}`
      ),
  },
}
