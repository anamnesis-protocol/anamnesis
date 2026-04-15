import { useState, useEffect } from 'react'

interface CalEvent {
  event_id: string
  title: string
  start: string
  end: string
  description: string
  location: string
  created_at: string
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

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return iso
  }
}

// Group events by date
function groupByDate(events: CalEvent[]): Record<string, CalEvent[]> {
  const groups: Record<string, CalEvent[]> = {}
  const sorted = [...events].sort((a, b) => a.start.localeCompare(b.start))
  for (const ev of sorted) {
    const day = ev.start.slice(0, 10)
    if (!groups[day]) groups[day] = []
    groups[day].push(ev)
  }
  return groups
}

export default function CalendarPage({ sessionId }: Props) {
  const [events, setEvents] = useState<CalEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState({
    title: '', start: '', end: '', description: '', location: '',
  })
  const [saving, setSaving] = useState(false)

  async function load() {
    setLoading(true)
    setError('')
    try {
      const data = await apiFetch(`/calendar/events?session_id=${sessionId}`)
      setEvents(data.events ?? [])
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      if (msg.includes('not found') || msg.includes('No calendar')) {
        try {
          await apiFetch('/calendar/init', {
            method: 'POST',
            body: JSON.stringify({ session_id: sessionId }),
          })
          setEvents([])
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

  async function handleAdd() {
    if (!form.title.trim() || !form.start.trim()) return
    setSaving(true)
    setError('')
    try {
      await apiFetch(`/calendar/event?session_id=${sessionId}`, {
        method: 'POST',
        body: JSON.stringify({ session_id: sessionId, ...form }),
      })
      setForm({ title: '', start: '', end: '', description: '', location: '' })
      setShowAdd(false)
      await load()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(eventId: string) {
    try {
      await apiFetch(`/calendar/event/${eventId}?session_id=${sessionId}`, { method: 'DELETE' })
      setEvents((prev) => prev.filter((e) => e.event_id !== eventId))
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const grouped = groupByDate(events)

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-auto p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-slate-100">📅 Arty Calendar</h2>
        <button onClick={() => setShowAdd((v) => !v)} className="btn-primary text-sm">
          {showAdd ? 'Cancel' : '+ Event'}
        </button>
      </div>

      {error && (
        <div className="text-red-400 text-xs bg-red-900/20 border border-red-800 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      {showAdd && (
        <div className="card space-y-3">
          <h3 className="text-sm font-medium text-slate-300">New event</h3>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Title</label>
            <input className="input" value={form.title}
              onChange={(e) => setForm((p) => ({ ...p, title: e.target.value }))} />
          </div>
          <div className="flex gap-2">
            <div className="flex-1">
              <label className="block text-xs text-slate-400 mb-1">Start</label>
              <input className="input" type="datetime-local" value={form.start}
                onChange={(e) => setForm((p) => ({ ...p, start: e.target.value }))} />
            </div>
            <div className="flex-1">
              <label className="block text-xs text-slate-400 mb-1">End (optional)</label>
              <input className="input" type="datetime-local" value={form.end}
                onChange={(e) => setForm((p) => ({ ...p, end: e.target.value }))} />
            </div>
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Location</label>
            <input className="input" value={form.location}
              onChange={(e) => setForm((p) => ({ ...p, location: e.target.value }))} />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Description</label>
            <textarea className="input resize-y min-h-[60px]" value={form.description}
              onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))} />
          </div>
          <button onClick={handleAdd} disabled={saving} className="btn-primary w-full">
            {saving ? 'Saving…' : 'Save event'}
          </button>
        </div>
      )}

      {loading ? (
        <div className="text-slate-500 text-sm">Loading…</div>
      ) : events.length === 0 ? (
        <div className="text-slate-500 text-sm">No events yet. Add your first event above.</div>
      ) : (
        <div className="space-y-4">
          {Object.entries(grouped).map(([day, dayEvents]) => (
            <div key={day}>
              <div className="text-xs text-slate-400 font-semibold mb-2 uppercase tracking-wider">
                {new Date(day + 'T00:00:00').toLocaleDateString(undefined, {
                  weekday: 'long', month: 'long', day: 'numeric',
                })}
              </div>
              <div className="space-y-2">
                {dayEvents.map((ev) => (
                  <div key={ev.event_id} className="card flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="font-medium text-slate-200">{ev.title}</div>
                      <div className="text-xs text-slate-400 mt-0.5">
                        {formatDate(ev.start)}
                        {ev.end && ` — ${formatDate(ev.end)}`}
                      </div>
                      {ev.location && (
                        <div className="text-xs text-slate-500 mt-0.5">📍 {ev.location}</div>
                      )}
                      {ev.description && (
                        <div className="text-xs text-slate-500 mt-1">{ev.description}</div>
                      )}
                    </div>
                    <button
                      onClick={() => handleDelete(ev.event_id)}
                      className="text-xs text-red-400 hover:text-red-300 shrink-0"
                    >
                      Delete
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
