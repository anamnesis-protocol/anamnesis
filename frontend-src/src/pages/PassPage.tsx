import { useState, useEffect } from 'react'

interface PassEntry {
  entry_id: string
  name: string
  username: string
  url: string
  notes: string
  created_at: string
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

// ─── Password generator ────────────────────────────────────────────────────────

const CHARSET = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()-_=+[]{}|;:,.<>?'

function generatePassword(length = 20): string {
  const arr = new Uint8Array(length)
  crypto.getRandomValues(arr)
  return Array.from(arr).map(b => CHARSET[b % CHARSET.length]).join('')
}

function passwordStrength(pw: string): { score: 0 | 1 | 2 | 3 | 4; label: string; color: string } {
  if (!pw) return { score: 0, label: '', color: '' }
  let score = 0
  if (pw.length >= 12) score++
  if (pw.length >= 20) score++
  if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) score++
  if (/[0-9]/.test(pw) && /[^a-zA-Z0-9]/.test(pw)) score++
  const map: Record<number, { label: string; color: string }> = {
    0: { label: 'Very weak', color: 'bg-red-500' },
    1: { label: 'Weak',      color: 'bg-orange-500' },
    2: { label: 'Fair',      color: 'bg-yellow-500' },
    3: { label: 'Strong',    color: 'bg-emerald-500' },
    4: { label: 'Very strong', color: 'bg-emerald-400' },
  }
  return { score: score as 0|1|2|3|4, ...map[score] }
}

export default function PassPage({ sessionId }: Props) {
  const [entries, setEntries] = useState<PassEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [revealId, setRevealId] = useState<string | null>(null)
  const [revealedPw, setRevealedPw] = useState<Record<string, string>>({})
  const [search, setSearch] = useState('')
  const [importing, setImporting] = useState(false)
  const [importError, setImportError] = useState('')

  // Add/edit form
  const [form, setForm] = useState({ name: '', username: '', password: '', url: '', notes: '' })
  const [saving, setSaving] = useState(false)
  const [showPw, setShowPw] = useState(false)

  async function load() {
    setLoading(true)
    setError('')
    try {
      const data = await apiFetch(`/pass/entries?session_id=${sessionId}`)
      setEntries(data.entries ?? [])
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      // If vault not initialized, init it
      if (msg.includes('not found') || msg.includes('No pass vault')) {
        try {
          await apiFetch(`/pass/init`, {
            method: 'POST',
            body: JSON.stringify({ session_id: sessionId }),
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

  async function handleSave() {
    if (!form.name.trim() || !form.password.trim()) return
    setSaving(true)
    setError('')
    try {
      if (editingId) {
        await apiFetch(`/pass/entry/${editingId}?session_id=${sessionId}`, {
          method: 'PATCH',
          body: JSON.stringify({ session_id: sessionId, ...form }),
        })
      } else {
        await apiFetch(`/pass/entry?session_id=${sessionId}`, {
          method: 'POST',
          body: JSON.stringify({ session_id: sessionId, ...form }),
        })
      }
      setForm({ name: '', username: '', password: '', url: '', notes: '' })
      setShowAdd(false)
      setEditingId(null)
      await load()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  async function handleEdit(entry: PassEntry) {
    try {
      const data = await apiFetch(`/pass/entry/${entry.entry_id}?session_id=${sessionId}`)
      setForm({
        name: entry.name,
        username: entry.username,
        url: entry.url,
        notes: entry.notes || '',
        password: data.password,
      })
      setEditingId(entry.entry_id)
      setShowAdd(true)
      setShowPw(false)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  function generate() {
    const pw = generatePassword(20)
    setForm(f => ({ ...f, password: pw }))
    setShowPw(true)
  }

  async function handleDelete(entryId: string) {
    try {
      await apiFetch(`/pass/entry/${entryId}?session_id=${sessionId}`, { method: 'DELETE' })
      setEntries((prev) => prev.filter((e) => e.entry_id !== entryId))
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function handleReveal(entryId: string) {
    if (revealedPw[entryId]) {
      setRevealId(revealId === entryId ? null : entryId)
      return
    }
    try {
      const data = await apiFetch(`/pass/entry/${entryId}?session_id=${sessionId}`)
      setRevealedPw((prev) => ({ ...prev, [entryId]: data.password }))
      setRevealId(entryId)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function handleImport(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return

    setImporting(true)
    setImportError('')

    try {
      const text = await file.text()
      const lines = text.split('\n').filter(line => line.trim())
      
      if (lines.length === 0) {
        setImportError('CSV file is empty')
        setImporting(false)
        return
      }

      const header = lines[0].toLowerCase()
      let format: 'arty' | 'proton' | 'lastpass' | 'bitwarden' | 'chrome' = 'arty'
      
      if (header.includes('vault') && header.includes('item name')) {
        format = 'proton'
      } else if (header.includes('folder') && header.includes('login_uri')) {
        format = 'bitwarden'
      } else if (header.includes('grouping') || header.includes('extra')) {
        format = 'lastpass'
      } else if (header.includes('name') && header.includes('url') && !header.includes('vault')) {
        format = 'chrome'
      }

      const dataLines = lines.slice(1)
      let imported = 0

      for (const line of dataLines) {
        if (!line.trim()) continue
        
        const fields: string[] = []
        let current = ''
        let inQuotes = false
        
        for (let i = 0; i < line.length; i++) {
          const char = line[i]
          if (char === '"') {
            inQuotes = !inQuotes
          } else if (char === ',' && !inQuotes) {
            fields.push(current.trim())
            current = ''
          } else {
            current += char
          }
        }
        fields.push(current.trim())

        let name = '', url = '', username = '', password = '', notes = ''

        if (format === 'proton') {
          name = fields[1] || ''
          notes = fields[2] || ''
          username = fields[3] || ''
          password = fields[4] || ''
          url = fields[5] || ''
        } else if (format === 'bitwarden') {
          name = fields[3] || ''
          notes = fields[4] || ''
          url = fields[7] || ''
          username = fields[8] || ''
          password = fields[9] || ''
        } else if (format === 'lastpass') {
          url = fields[0] || ''
          username = fields[1] || ''
          password = fields[2] || ''
          notes = fields[3] || ''
          name = fields[4] || ''
        } else if (format === 'chrome') {
          name = fields[0] || ''
          url = fields[1] || ''
          username = fields[2] || ''
          password = fields[3] || ''
        } else {
          name = fields[0] || ''
          url = fields[1] || ''
          username = fields[2] || ''
          password = fields[3] || ''
          notes = fields[4] || ''
        }

        if (!name || !password) continue

        const res = await apiFetch(`/pass/entry?session_id=${sessionId}`, {
          method: 'POST',
          body: JSON.stringify({ session_id: sessionId, name, url, username, password, notes }),
        })
        if (res) imported++
      }

      setImporting(false)
      load()
      alert(`Successfully imported ${imported} passwords from ${format === 'arty' ? 'CSV' : format.charAt(0).toUpperCase() + format.slice(1)} format`)
    } catch (err) {
      setImportError('Failed to parse CSV file. Supported formats: Proton Pass, 1Password, LastPass, Bitwarden, Chrome, or Arty Pass')
      setImporting(false)
    }

    event.target.value = ''
  }

  async function handleExport() {
    const rows = [['name', 'url', 'username', 'password', 'notes']]
    
    for (const entry of entries) {
      const res = await apiFetch(`/pass/entry/${entry.entry_id}?session_id=${sessionId}`)
      rows.push([entry.name, entry.url, entry.username, res.password, entry.notes || ''])
    }

    const csv = rows.map(row => row.map(cell => `"${cell}"`).join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `arty-pass-export-${new Date().toISOString().split('T')[0]}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const filtered = entries.filter(e =>
    e.name.toLowerCase().includes(search.toLowerCase()) ||
    e.username.toLowerCase().includes(search.toLowerCase())
  )

  const strength = passwordStrength(form.password)

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-auto p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-slate-100">🔑 Arty Pass</h2>
        <div className="flex gap-2">
          <label className="btn-secondary text-xs cursor-pointer">
            ↑ Import
            <input type="file" accept=".csv" onChange={handleImport} disabled={importing} className="hidden" />
          </label>
          <button onClick={handleExport} disabled={entries.length === 0} className="btn-secondary text-xs">
            ↓ Export
          </button>
          <button onClick={() => { setShowAdd((v) => !v); setEditingId(null); setForm({ name: '', username: '', password: '', url: '', notes: '' }) }} className="btn-primary text-sm">
            {showAdd ? 'Cancel' : '+ Add'}
          </button>
        </div>
      </div>

      {!showAdd && (
        <div className="relative">
          <input
            type="text"
            placeholder="Search entries…"
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

      {importing && (
        <div className="text-violet-400 text-xs bg-violet-900/20 border border-violet-800 rounded-lg px-3 py-2 text-center">
          Importing passwords...
        </div>
      )}

      {importError && (
        <div className="text-red-400 text-xs bg-red-900/20 border border-red-800 rounded-lg px-3 py-2">
          {importError}
          <button onClick={() => setImportError('')} className="ml-2 underline">Dismiss</button>
        </div>
      )}

      {showAdd && (
        <div className="card space-y-3">
          <h3 className="text-sm font-medium text-slate-300">{editingId ? 'Edit entry' : 'New entry'}</h3>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Name</label>
            <input
              className="input"
              type="text"
              value={form.name}
              onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
              placeholder="e.g. Gmail"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Username</label>
            <input
              className="input"
              type="text"
              value={form.username}
              onChange={(e) => setForm((prev) => ({ ...prev, username: e.target.value }))}
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Password</label>
            <div className="relative">
              <input
                className="input pr-16"
                type={showPw ? 'text' : 'password'}
                value={form.password}
                onChange={(e) => setForm((prev) => ({ ...prev, password: e.target.value }))}
              />
              <button
                type="button"
                onClick={generate}
                className="absolute right-8 top-1/2 -translate-y-1/2 text-slate-500 hover:text-violet-400 text-xs"
                title="Generate password"
              >
                ⟳
              </button>
              <button
                type="button"
                onClick={() => setShowPw(v => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 text-xs"
              >
                {showPw ? '👁' : '👁‍🗨'}
              </button>
            </div>
            {form.password && (
              <div className="mt-1.5 flex items-center gap-2">
                <div className="flex gap-0.5 flex-1">
                  {[0,1,2,3].map(i => (
                    <div key={i} className={`h-0.5 flex-1 rounded-full transition-colors ${i < strength.score ? strength.color : 'bg-white/10'}`} />
                  ))}
                </div>
                <span className="text-xs text-slate-500">{strength.label}</span>
              </div>
            )}
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">URL</label>
            <input
              className="input"
              type="text"
              value={form.url}
              onChange={(e) => setForm((prev) => ({ ...prev, url: e.target.value }))}
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Notes</label>
            <textarea
              className="input"
              rows={2}
              value={form.notes}
              onChange={(e) => setForm((prev) => ({ ...prev, notes: e.target.value }))}
            />
          </div>
          <button onClick={handleSave} disabled={saving || !form.name.trim() || !form.password.trim()} className="btn-primary w-full">
            {saving ? 'Saving…' : editingId ? 'Update entry' : 'Save entry'}
          </button>
        </div>
      )}

      {loading ? (
        <div className="text-slate-500 text-sm">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="text-slate-500 text-sm">{search ? 'No entries match.' : 'No entries yet. Add your first password above.'}</div>
      ) : (
        <div className="space-y-2">
          {filtered.map((entry) => (
            <div key={entry.entry_id} className="card space-y-1">
              <div className="flex items-center justify-between">
                <span className="font-medium text-slate-200">{entry.name}</span>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleEdit(entry)}
                    className="text-xs text-slate-400 hover:text-slate-200"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => handleReveal(entry.entry_id)}
                    className="text-xs text-slate-400 hover:text-slate-200"
                  >
                    {revealId === entry.entry_id ? 'Hide' : 'Show pw'}
                  </button>
                  <button
                    onClick={() => handleDelete(entry.entry_id)}
                    className="text-xs text-red-400 hover:text-red-300"
                  >
                    Delete
                  </button>
                </div>
              </div>
              {entry.username && (
                <div className="text-xs text-slate-400">{entry.username}</div>
              )}
              {entry.url && (
                <div className="text-xs text-slate-500 truncate">{entry.url}</div>
              )}
              {revealId === entry.entry_id && revealedPw[entry.entry_id] && (
                <div className="mono text-xs text-emerald-400 bg-emerald-900/20 rounded px-2 py-1">
                  {revealedPw[entry.entry_id]}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
