import { useState, useEffect } from 'react'

interface TOTPEntry {
  id: string
  name: string
  issuer: string | null
  secret: string
  updated_at: string
}

interface Props {
  sessionId: string
}

const BASE = import.meta.env.VITE_API_BASE ?? ''

async function apiFetch(path: string, opts?: RequestInit) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? `HTTP ${res.status}`)
  }
  return res.json()
}

// ─── TOTP generation (RFC 6238) ────────────────────────────────────────────

function base32Decode(base32: string): Uint8Array {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
  const cleanInput = base32.toUpperCase().replace(/[^A-Z2-7]/g, '')
  const bits: number[] = []
  for (const char of cleanInput) {
    const val = alphabet.indexOf(char)
    if (val === -1) continue
    for (let i = 4; i >= 0; i--) bits.push((val >> i) & 1)
  }
  const bytes: number[] = []
  for (let i = 0; i + 8 <= bits.length; i += 8) {
    bytes.push(bits.slice(i, i + 8).reduce((acc, bit) => (acc << 1) | bit, 0))
  }
  return new Uint8Array(bytes)
}

async function generateTOTP(secret: string, timeStep = 30): Promise<string> {
  const key = base32Decode(secret)
  const counter = Math.floor(Date.now() / 1000 / timeStep)
  const counterBytes = new ArrayBuffer(8)
  const view = new DataView(counterBytes)
  view.setUint32(4, counter, false)
  
  const cryptoKey = await crypto.subtle.importKey(
    'raw',
    key as BufferSource,
    { name: 'HMAC', hash: 'SHA-1' },
    false,
    ['sign']
  )
  
  const signature = await crypto.subtle.sign('HMAC', cryptoKey, counterBytes as BufferSource)
  const hash = new Uint8Array(signature)
  const offset = hash[hash.length - 1] & 0x0f
  const binary = ((hash[offset] & 0x7f) << 24) |
                 ((hash[offset + 1] & 0xff) << 16) |
                 ((hash[offset + 2] & 0xff) << 8) |
                 (hash[offset + 3] & 0xff)
  const otp = binary % 1000000
  return otp.toString().padStart(6, '0')
}

function useCountdown(interval = 30): number {
  const [remaining, setRemaining] = useState(interval - (Math.floor(Date.now() / 1000) % interval))
  useEffect(() => {
    const timer = setInterval(() => {
      setRemaining(interval - (Math.floor(Date.now() / 1000) % interval))
    }, 100)
    return () => clearInterval(timer)
  }, [interval])
  return remaining
}

export default function AuthenticatorPage({ sessionId }: Props) {
  const [entries, setEntries] = useState<TOTPEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const [search, setSearch] = useState('')

  // Form state
  const [form, setForm] = useState({ name: '', secret: '', issuer: '' })
  const [saving, setSaving] = useState(false)

  // TOTP codes
  const [codes, setCodes] = useState<Record<string, string>>({})
  const [copied, setCopied] = useState<string | null>(null)

  const remaining = useCountdown(30)

  async function load() {
    setLoading(true)
    setError('')
    try {
      const data = await apiFetch(`/pass/totp?session_id=${sessionId}`)
      setEntries(data.entries ?? [])
      
      // Generate codes for all entries
      const newCodes: Record<string, string> = {}
      for (const entry of data.entries ?? []) {
        try {
          newCodes[entry.id] = await generateTOTP(entry.secret)
        } catch (e) {
          console.error(`Failed to generate TOTP for ${entry.name}:`, e)
          newCodes[entry.id] = '------'
        }
      }
      setCodes(newCodes)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      if (msg.includes('not found') || msg.includes('No totp vault')) {
        try {
          await apiFetch(`/pass/totp`, {
            method: 'POST',
            body: JSON.stringify({ action: 'init', session_id: sessionId }),
          })
          setEntries([])
        } catch {
          setError(msg)
        }
      } else {
        setError(msg)
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [sessionId])

  // Regenerate codes every second
  useEffect(() => {
    const timer = setInterval(async () => {
      const newCodes: Record<string, string> = {}
      for (const entry of entries) {
        try {
          newCodes[entry.id] = await generateTOTP(entry.secret)
        } catch (e) {
          newCodes[entry.id] = '------'
        }
      }
      setCodes(newCodes)
    }, 1000)
    return () => clearInterval(timer)
  }, [entries])

  async function handleSave() {
    if (!form.name.trim() || !form.secret.trim()) return
    setSaving(true)
    setError('')
    try {
      await apiFetch(`/pass/totp`, {
        method: 'POST',
        body: JSON.stringify({
          session_id: sessionId,
          name: form.name,
          secret: form.secret.replace(/\s/g, '').toUpperCase(),
          issuer: form.issuer || null,
        }),
      })
      setForm({ name: '', secret: '', issuer: '' })
      setShowAdd(false)
      await load()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(entryId: string) {
    try {
      await apiFetch(`/pass/totp/${entryId}?session_id=${sessionId}`, { method: 'DELETE' })
      setEntries((prev) => prev.filter((e) => e.id !== entryId))
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function handleCopy(entryId: string) {
    const code = codes[entryId]
    if (!code) return
    await navigator.clipboard.writeText(code)
    setCopied(entryId)
    setTimeout(() => setCopied(null), 2000)
  }

  const filtered = entries.filter(e =>
    e.name.toLowerCase().includes(search.toLowerCase()) ||
    (e.issuer && e.issuer.toLowerCase().includes(search.toLowerCase()))
  )

  const progress = (remaining / 30) * 100

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-auto p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-slate-100">🔐 Authenticator</h2>
        <button onClick={() => { setShowAdd((v) => !v); setForm({ name: '', secret: '', issuer: '' }) }} className="btn-primary text-sm">
          {showAdd ? 'Cancel' : '+ Add'}
        </button>
      </div>

      {!showAdd && (
        <div className="relative">
          <input
            type="text"
            placeholder="Search authenticators…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="input text-sm w-full"
          />
        </div>
      )}

      {error && (
        <div className="text-red-400 text-xs bg-red-900/20 border border-red-800 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      {showAdd && (
        <div className="card space-y-3">
          <h3 className="text-sm font-medium text-slate-300">Add authenticator</h3>
          
          <div>
            <label className="block text-xs text-slate-400 mb-1">Account name</label>
            <input className="input" value={form.name} onChange={e => setForm({...form, name: e.target.value})} placeholder="e.g. GitHub" />
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">Secret key</label>
            <input className="input mono" value={form.secret} onChange={e => setForm({...form, secret: e.target.value})} placeholder="Base32 secret from QR code" />
            <p className="text-xs text-slate-500 mt-1">Enter the secret key shown when setting up 2FA</p>
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">Issuer (optional)</label>
            <input className="input" value={form.issuer} onChange={e => setForm({...form, issuer: e.target.value})} placeholder="e.g. GitHub" />
          </div>

          <button onClick={handleSave} disabled={saving || !form.name.trim() || !form.secret.trim()} className="btn-primary w-full">
            {saving ? 'Adding…' : 'Add authenticator'}
          </button>
        </div>
      )}

      {loading ? (
        <div className="text-slate-500 text-sm">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="text-slate-500 text-sm">{search ? 'No authenticators match.' : 'No authenticators yet. Add your first one above.'}</div>
      ) : (
        <div className="space-y-3">
          {filtered.map((entry) => (
            <div key={entry.id} className="card">
              <div className="flex items-center justify-between mb-2">
                <div>
                  <div className="font-medium text-slate-200">{entry.name}</div>
                  {entry.issuer && <div className="text-xs text-slate-500">{entry.issuer}</div>}
                </div>
                <button onClick={() => handleDelete(entry.id)} className="text-xs text-red-400 hover:text-red-300">
                  Delete
                </button>
              </div>

              <div className="flex items-center gap-3">
                <div className="relative w-12 h-12 flex-shrink-0">
                  <svg className="w-12 h-12 -rotate-90">
                    <circle cx="24" cy="24" r="20" stroke="currentColor" strokeWidth="3" fill="none" className="text-white/10" />
                    <circle
                      cx="24"
                      cy="24"
                      r="20"
                      stroke="currentColor"
                      strokeWidth="3"
                      fill="none"
                      strokeDasharray={`${2 * Math.PI * 20}`}
                      strokeDashoffset={`${2 * Math.PI * 20 * (1 - progress / 100)}`}
                      className="text-violet-500 transition-all duration-100"
                    />
                  </svg>
                  <div className="absolute inset-0 flex items-center justify-center text-xs font-medium text-slate-400">
                    {remaining}s
                  </div>
                </div>

                <div className="flex-1">
                  <div className="mono text-2xl font-bold text-slate-100 tracking-wider">
                    {codes[entry.id] || '------'}
                  </div>
                </div>

                <button
                  onClick={() => handleCopy(entry.id)}
                  className="btn-secondary text-xs"
                  disabled={!codes[entry.id]}
                >
                  {copied === entry.id ? '✓ Copied' : 'Copy'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
