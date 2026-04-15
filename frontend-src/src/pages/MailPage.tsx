import { useState, useEffect } from 'react'

interface MailMessage {
  message_id: string
  sender_token_id: string
  recipient_token_id: string
  subject: string
  body: string
  sent_at: string
  read: boolean
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

export default function MailPage({ sessionId }: Props) {
  const [messages, setMessages] = useState<MailMessage[]>([])
  const [selected, setSelected] = useState<MailMessage | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showCompose, setShowCompose] = useState(false)
  const [form, setForm] = useState({ recipient_token_id: '', subject: '', body: '' })
  const [sending, setSending] = useState(false)

  async function load() {
    setLoading(true)
    setError('')
    try {
      const data = await apiFetch(`/mail/messages?session_id=${sessionId}`)
      setMessages(data.messages ?? [])
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      if (msg.includes('not found') || msg.includes('No mail')) {
        try {
          await apiFetch('/mail/init', {
            method: 'POST',
            body: JSON.stringify({ session_id: sessionId }),
          })
          setMessages([])
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

  async function handleSend() {
    if (!form.recipient_token_id.trim() || !form.body.trim()) return
    setSending(true)
    setError('')
    try {
      await apiFetch(`/mail/send?session_id=${sessionId}`, {
        method: 'POST',
        body: JSON.stringify({ session_id: sessionId, ...form }),
      })
      setForm({ recipient_token_id: '', subject: '', body: '' })
      setShowCompose(false)
      await load()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSending(false)
    }
  }

  async function handleDelete(messageId: string) {
    try {
      await apiFetch(`/mail/message/${messageId}?session_id=${sessionId}`, { method: 'DELETE' })
      setMessages((prev) => prev.filter((m) => m.message_id !== messageId))
      if (selected?.message_id === messageId) setSelected(null)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <div className="flex-1 flex min-h-0 overflow-hidden">
      {/* Message list */}
      <div className="flex flex-col w-64 shrink-0 border-r border-surface-border min-h-0">
        <div className="flex items-center justify-between p-3 border-b border-surface-border">
          <span className="text-sm font-semibold text-slate-200">✉️ Arty Mail</span>
          <button onClick={() => setShowCompose((v) => !v)} className="btn-primary text-xs py-1 px-2">
            Compose
          </button>
        </div>
        {error && (
          <div className="text-red-400 text-xs px-3 py-2">{error}</div>
        )}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="text-slate-500 text-xs p-3">Loading…</div>
          ) : messages.length === 0 ? (
            <div className="text-slate-500 text-xs p-3">No messages yet.</div>
          ) : (
            messages.map((m) => (
              <button
                key={m.message_id}
                onClick={() => setSelected(m)}
                className={`w-full text-left p-3 border-b border-surface-border hover:bg-white/5 transition-colors ${
                  selected?.message_id === m.message_id ? 'bg-brand/10' : ''
                }`}
              >
                <div className="text-xs font-medium text-slate-200 truncate">
                  {m.subject || '(no subject)'}
                </div>
                <div className="text-xs text-slate-500 truncate">
                  {m.sender_token_id}
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Message detail / compose */}
      <div className="flex-1 p-6 overflow-auto space-y-4">
        {showCompose ? (
          <div className="space-y-3 max-w-xl">
            <h3 className="text-sm font-semibold text-slate-200">New message</h3>
            <div>
              <label className="block text-xs text-slate-400 mb-1">To (token ID)</label>
              <input
                className="input"
                placeholder="0.0.12345"
                value={form.recipient_token_id}
                onChange={(e) => setForm((p) => ({ ...p, recipient_token_id: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Subject</label>
              <input
                className="input"
                value={form.subject}
                onChange={(e) => setForm((p) => ({ ...p, subject: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Body</label>
              <textarea
                className="input min-h-[120px] resize-y"
                value={form.body}
                onChange={(e) => setForm((p) => ({ ...p, body: e.target.value }))}
              />
            </div>
            <div className="flex gap-2">
              <button onClick={handleSend} disabled={sending} className="btn-primary">
                {sending ? 'Sending…' : 'Send'}
              </button>
              <button onClick={() => setShowCompose(false)} className="btn-ghost">
                Cancel
              </button>
            </div>
          </div>
        ) : selected ? (
          <div className="space-y-4 max-w-xl">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="text-base font-semibold text-slate-200">
                  {selected.subject || '(no subject)'}
                </h3>
                <div className="text-xs text-slate-500 mt-1">
                  From: {selected.sender_token_id} · {new Date(selected.sent_at).toLocaleString()}
                </div>
              </div>
              <button
                onClick={() => handleDelete(selected.message_id)}
                className="text-xs text-red-400 hover:text-red-300 shrink-0"
              >
                Delete
              </button>
            </div>
            <div className="text-sm text-slate-300 whitespace-pre-wrap border border-surface-border rounded-lg p-4 bg-surface-card">
              {selected.body}
            </div>
          </div>
        ) : (
          <div className="text-slate-500 text-sm">Select a message or compose a new one.</div>
        )}
      </div>
    </div>
  )
}
