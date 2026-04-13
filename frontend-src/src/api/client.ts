/**
 * api/client.ts — typed wrappers around the Sovereign AI Context API.
 */

const BASE = import.meta.env.VITE_API_BASE ?? ''

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
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
  context_sections: Record<string, string>
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

// ---------------------------------------------------------------------------
// Vault health
// ---------------------------------------------------------------------------

export type HealthStatus = 'pass' | 'warn' | 'critical' | 'unavailable'
export type VaultOverall = 'healthy' | 'degraded' | 'critical'

export interface VaultHealthResponse {
  session_id: string
  token_id: string
  overall: VaultOverall
  sections_loaded: string[]
  checks: {
    completeness: {
      status: HealthStatus
      sections_present: string[]
      sections_missing: string[]
      sections_empty: string[]
    }
    size: {
      status: HealthStatus
      sections: Array<{ section: string; chars: number; tokens_estimate: number; issue: string | null }>
    }
    structure: {
      status: HealthStatus
      issues: Array<{ section: string; issues: string[] }>
    }
    staleness: {
      status: HealthStatus
      last_date: string | null
      days_since_update: number | null
      note: string
      warn_threshold_days: number
      critical_threshold_days: number
    }
    metadata: {
      status: HealthStatus
      issues: Array<{ section: string; issues: string[] }>
    }
    duplicate_content: {
      status: HealthStatus
      duplicate_count: number
      duplicates: Array<{ sections: string[]; preview: string }>
      note: string
    }
    rag_index: {
      status: HealthStatus
      chunks: number
      avg_chars_per_chunk: number
      tiny_chunks: number
      oversized_chunks: number
      note: string
    }
    session_state_growth: {
      status: HealthStatus
      chars: number
      tokens_estimate: number
      warn_threshold_chars: number
      critical_threshold_chars: number
      note: string
    }
    hfs_registry: {
      status: HealthStatus
      registered_sections: string[]
      unregistered_sections: string[]
      index_file_id: string
    }
  }
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
// Session
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

  // ---------------------------------------------------------------------------
  // User provisioning
  // ---------------------------------------------------------------------------
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

  // ---------------------------------------------------------------------------
  // Chat
  // ---------------------------------------------------------------------------
  chat: {
    models: (session_id?: string) => {
      const qs = session_id ? `?session_id=${session_id}` : ''
      return request<{ models: ModelInfo[] }>('GET', `/chat/models${qs}`)
    },

    setKeys: (session_id: string, keys: Record<string, string>) =>
      request<{ configured: string[] }>('POST', '/chat/keys', { session_id, keys }),

    /** Returns a ReadableStream of SSE tokens. Caller handles streaming. */
    streamMessage: (
      session_id: string,
      message: string,
      model: string,
      history: Array<{ role: string; content: string }> = []
    ): Promise<Response> =>
      fetch(`${BASE}/chat/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id, message, model, history }),
      }),
  },

  // ---------------------------------------------------------------------------
  // Vault
  // ---------------------------------------------------------------------------
  vault: {
    health: (session_id: string) =>
      request<VaultHealthResponse>('GET', `/vault/health?session_id=${encodeURIComponent(session_id)}`),

    repair: (session_id: string) =>
      request<{ repairs_applied: number; fixed: number; improved: number; failed: number; repairs: Array<Record<string, unknown>>; note: string }>(
        'POST', `/vault/health/repair?session_id=${encodeURIComponent(session_id)}`
      ),
  },

  // ---------------------------------------------------------------------------
  // Skills
  // ---------------------------------------------------------------------------
  skills: {
    list: (session_id: string, tags?: string, name_contains?: string) => {
      const params = new URLSearchParams({ session_id })
      if (tags) params.set('tags', tags)
      if (name_contains) params.set('name_contains', name_contains)
      return request<{ token_id: string; skills: SkillSummary[] }>('GET', `/skills?${params}`)
    },

    get: (skill_id: string, session_id: string) =>
      request<SkillDetail>('GET', `/skills/${skill_id}?session_id=${session_id}`),

    upsert: (session_id: string, data: Partial<SkillDetail> & { name: string; description: string; instructions: string }) =>
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
